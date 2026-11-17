"""
src/graph/store.py

Thread-safe, append-only in-memory storage for Case Graph events.

Enforces:
- Chronological, monotonic sequence numbering per encounter.
- Append-only immutability (events cannot be deleted or modified).
- Encounter isolation (events for different encounters are physically separated).
- Optimistic concurrency control via expected_version.
- Audit replay capability to rebuild case state at any version.
"""

from __future__ import annotations

import copy
import threading
from typing import Dict, List, Optional

from src.common.errors import EventReplayError, StaleVersion
from src.common.models import (
    Claim,
    Edge,
    Event,
    Finding,
    Hypothesis,
    PatientContext,
    Verdict,
)
from src.graph.events import EventType
from src.graph.view import CaseView


class EventStore:
    """In-memory append-only event store partitioned by encounter_id."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._events: Dict[str, List[Event]] = {}

    def get_events(self, encounter_id: str, since_sequence: Optional[int] = None) -> List[Event]:
        """Return events for an encounter in strict chronological order."""
        with self._lock:
            enc_events = self._events.get(encounter_id, [])
            if since_sequence is None:
                return [e.model_copy(deep=True) for e in enc_events]
            return [e.model_copy(deep=True) for e in enc_events if e.sequence > since_sequence]

    def get_current_version(self, encounter_id: str) -> int:
        """Return the current version (count of events) for the encounter."""
        with self._lock:
            return len(self._events.get(encounter_id, []))

    def append_event(
        self,
        event: Event,
        expected_version: Optional[int] = None,
    ) -> Event:
        """Append an event to the log.

        Raises:
            StaleVersion: If expected_version is specified and does not match current version.
            ValueError: If event encounter_id or sequence violates monotonic integrity.
        """
        with self._lock:
            enc_id = event.encounter_id
            enc_events = self._events.setdefault(enc_id, [])
            current_version = len(enc_events)

            if expected_version is not None and expected_version != current_version:
                raise StaleVersion(
                    encounter_id=enc_id,
                    expected_version=expected_version,
                    current_version=current_version,
                )

            expected_seq = current_version + 1
            if event.sequence != expected_seq:
                raise ValueError(
                    f"Invalid event sequence {event.sequence}; expected {expected_seq} "
                    f"for encounter '{enc_id}'."
                )

            # Check for duplicate event_id across all events for this encounter
            for existing in enc_events:
                if existing.event_id == event.event_id:
                    raise ValueError(
                        f"Duplicate event_id '{event.event_id}' for encounter '{enc_id}'."
                    )

            stored_event = event.model_copy(deep=True)
            enc_events.append(stored_event)
            return stored_event

    def replay(self, encounter_id: str, target_version: Optional[int] = None) -> CaseView:
        """Reconstruct the CaseView by sequentially replaying events from sequence 1.

        Guarantees that state is reconstructed deterministically from the immutable event log.
        """
        with self._lock:
            all_events = self._events.get(encounter_id, [])
            if target_version is not None:
                events_to_replay = [e for e in all_events if e.sequence <= target_version]
            else:
                events_to_replay = all_events

            context: Optional[PatientContext] = None
            findings_map: Dict[str, Finding] = {}
            hypotheses_map: Dict[str, Hypothesis] = {}
            claims_map: Dict[str, Claim] = {}
            verdicts_map: Dict[str, Verdict] = {}
            edges_map: Dict[str, Edge] = {}

            for event in events_to_replay:
                try:
                    ev_type = event.type
                    payload = event.payload

                    if ev_type == EventType.CONTEXT_SET.value:
                        context = PatientContext.model_validate(payload)

                    elif ev_type == EventType.FINDING_ADDED.value:
                        finding = Finding.model_validate(payload)
                        findings_map[finding.id] = finding

                    elif ev_type in {
                        EventType.FINDING_CONFIRMED.value,
                        EventType.FINDING_REJECTED.value,
                        EventType.FINDING_EDITED.value,
                    }:
                        finding_id = event.target or payload.get("id")
                        if not finding_id or finding_id not in findings_map:
                            raise EventReplayError(f"Target finding '{finding_id}' not found for event {event.event_id}")
                        # Updated finding is in payload or event.after
                        updated_finding = Finding.model_validate(payload)
                        findings_map[finding_id] = updated_finding

                    elif ev_type == EventType.HYPOTHESIS_ADDED.value:
                        hypothesis = Hypothesis.model_validate(payload)
                        hypotheses_map[hypothesis.id] = hypothesis

                    elif ev_type in {
                        EventType.HYPOTHESIS_STATUS_CHANGED.value,
                        EventType.HYPOTHESIS_RESCORED.value,
                    }:
                        hyp_id = event.target or payload.get("id")
                        if not hyp_id or hyp_id not in hypotheses_map:
                            raise EventReplayError(f"Target hypothesis '{hyp_id}' not found for event {event.event_id}")
                        updated_hyp = Hypothesis.model_validate(payload)
                        hypotheses_map[hyp_id] = updated_hyp

                    elif ev_type == EventType.CLAIM_ADDED.value:
                        claim = Claim.model_validate(payload)
                        claims_map[claim.claim_id] = claim

                    elif ev_type == EventType.VERDICT_ADDED.value:
                        verdict = Verdict.model_validate(payload)
                        verdicts_map[verdict.verdict_id] = verdict

                    elif ev_type == EventType.EDGE_ADDED.value:
                        edge = Edge.model_validate(payload)
                        edges_map[edge.id] = edge

                    else:
                        raise EventReplayError(f"Unknown event type '{ev_type}' in event {event.event_id}")

                except Exception as exc:
                    raise EventReplayError(
                        f"Error replaying event {event.event_id} (seq={event.sequence}): {exc}"
                    ) from exc

            return CaseView(
                encounter_id=encounter_id,
                version=len(events_to_replay),
                context=context,
                findings=list(findings_map.values()),
                hypotheses=list(hypotheses_map.values()),
                claims=list(claims_map.values()),
                verdicts=list(verdicts_map.values()),
                edges=list(edges_map.values()),
            )
