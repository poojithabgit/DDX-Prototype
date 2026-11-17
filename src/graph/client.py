"""
src/graph/client.py

Scoped Case Graph Client enforcing writer permissions and schema validation.
Implements GraphClient from docs/INTERFACES.md section 3 and docs/04-case-graph.md section 5.

Permissions matrix:
- Ingestion: Finding, contradicts edges
- Checkpoint 1 (clinician): Confirmation status, edited values
- Proposer (LLM): Hypothesis (origin = LLM), Claim
- KB lookup: Hypothesis (origin = KB or MNM)
- Verifiers: Verdict
- Scorer: prior, posterior, band on Hypothesis (update_scores)
- Planner: Edge (discriminates, recommends, etc.)
- Clinician (checkpoint 2): Hypothesis status, decisions
"""

from __future__ import annotations

import json
import os
from typing import Any, List, Optional
import jsonschema
from jsonschema import Draft202012Validator

from src.common.clock import Clock, IdFactory
from src.common.errors import PermissionDenied, SchemaValidationError
from src.common.models import (
    Claim,
    Confirmation,
    Edge,
    Event,
    Finding,
    Hypothesis,
    PatientContext,
    Verdict,
)
from src.common.types import (
    Band,
    ConfirmationStatus,
    HypothesisOrigin,
    HypothesisStatus,
    TrustTier,
)
from src.graph.events import EventType
from src.graph.store import EventStore
from src.graph.view import CaseView

# Load schemas once for runtime schema validation on write
_SCHEMAS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "schemas")


def _load_validator(filename: str) -> Draft202012Validator:
    path = os.path.join(_SCHEMAS_DIR, filename)
    with open(path, encoding="utf-8") as f:
        schema = json.load(f)
    return Draft202012Validator(schema)


_VALIDATORS = {
    "finding": _load_validator("finding.schema.json"),
    "hypothesis": _load_validator("hypothesis.schema.json"),
    "claim": _load_validator("claim.schema.json"),
    "verdict": _load_validator("verdict.schema.json"),
}


def _validate_schema(name: str, model_instance: Any) -> None:
    validator = _VALIDATORS.get(name)
    if validator:
        data = model_instance.model_dump(mode="json", exclude_none=True)
        try:
            validator.validate(data)
        except jsonschema.ValidationError as exc:
            raise SchemaValidationError(name, exc.message) from exc


class GraphClient:
    """Scoped Case Graph Client for a specific component and encounter."""

    def __init__(
        self,
        component: str,
        component_version: str,
        encounter_id: str,
        db: EventStore,
        clock: Clock,
        id_factory: IdFactory,
    ) -> None:
        self.component = component
        self.component_version = component_version
        self.actor = f"{component}@{component_version}"
        self.encounter_id = encounter_id
        self.db = db
        self.clock = clock
        self.id_factory = id_factory

    # -----------------------------------------------------------------------
    # Reads (allowed for all components)
    # -----------------------------------------------------------------------

    def view(self) -> CaseView:
        """Return an immutable snapshot of the current case state."""
        return self.db.replay(self.encounter_id)

    def events(self, since: Optional[str] = None) -> List[Event]:
        """Return raw event sequence for this encounter."""
        all_events = self.db.get_events(self.encounter_id)
        if since is None:
            return all_events
        return [e for e in all_events if e.event_id > since]

    # -----------------------------------------------------------------------
    # Writes (permission-checked, schema-validated, append-only)
    # -----------------------------------------------------------------------

    def set_context(self, context: PatientContext, expected_version: Optional[int] = None) -> PatientContext:
        """Set patient context. Allowed for ingestion, clinician, and orchestrator."""
        allowed = {"ingestion", "clinician", "checkpoint_1", "checkpoint_2", "orchestrator", "test"}
        if self.component not in allowed:
            raise PermissionDenied(self.component, "set_context")

        current_ver = self.db.get_current_version(self.encounter_id)
        event = Event(
            event_id=self.id_factory.next_id("ev"),
            encounter_id=self.encounter_id,
            sequence=current_ver + 1,
            at=self.clock.now_iso(),
            actor=self.actor,
            type=EventType.CONTEXT_SET.value,
            target=context.patient_id,
            payload=context.model_dump(mode="json"),
        )
        self.db.append_event(event, expected_version=expected_version)
        return context

    def add_finding(self, finding: Finding, expected_version: Optional[int] = None) -> Finding:
        """Add a finding to the Case Graph.

        Permissions: Ingestion, imaging service, or test.
        """
        allowed = {"ingestion", "imaging", "imaging_service", "test"}
        if self.component not in allowed:
            raise PermissionDenied(self.component, "add_finding")

        if finding.encounter_id != self.encounter_id:
            raise ValueError(
                f"Finding encounter_id '{finding.encounter_id}' does not match client encounter '{self.encounter_id}'"
            )

        # Schema validation
        _validate_schema("finding", finding)

        # Enforce duplicate prevention per encounter
        current_view = self.view()
        if current_view.finding_by_id(finding.id) is not None:
            raise ValueError(f"Finding with id '{finding.id}' already exists in encounter '{self.encounter_id}'.")

        current_ver = self.db.get_current_version(self.encounter_id)
        event = Event(
            event_id=self.id_factory.next_id("ev"),
            encounter_id=self.encounter_id,
            sequence=current_ver + 1,
            at=self.clock.now_iso(),
            actor=self.actor,
            type=EventType.FINDING_ADDED.value,
            target=finding.id,
            payload=finding.model_dump(mode="json"),
        )
        self.db.append_event(event, expected_version=expected_version)
        return finding

    def confirm_finding(
        self,
        finding_id: str,
        by: str,
        edited: Optional[Finding] = None,
        expected_version: Optional[int] = None,
    ) -> Finding:
        """Clinician confirmation of a finding at Checkpoint 1.

        Permissions: checkpoint_1, clinician, or test.
        Safety: Never automatically promotes T6 to a higher tier; preserves provenance.
        """
        allowed = {"checkpoint_1", "clinician", "test"}
        if self.component not in allowed:
            raise PermissionDenied(self.component, "confirm_finding")

        if not by or not by.strip():
            raise ValueError(
                "Clinician identity 'by' is required and cannot be empty or whitespace."
            )

        current_view = self.view()
        existing = current_view.finding_by_id(finding_id)
        if existing is None:
            raise ValueError(f"Finding '{finding_id}' not found in encounter '{self.encounter_id}'.")

        now_iso = self.clock.now_iso()

        if edited is not None:
            # Finding edited by clinician
            _validate_schema("finding", edited)
            new_confirmation = Confirmation(
                status=ConfirmationStatus.EDITED,
                by=by,
                at=now_iso,
                original_value=existing.value,
            )
            updated_finding = edited.model_copy(
                update={"confirmation": new_confirmation}
            )
            ev_type = EventType.FINDING_EDITED.value
        else:
            # Finding confirmed as-is
            new_confirmation = Confirmation(
                status=ConfirmationStatus.CONFIRMED,
                by=by,
                at=now_iso,
            )
            updated_finding = existing.model_copy(
                update={"confirmation": new_confirmation}
            )
            ev_type = EventType.FINDING_CONFIRMED.value

        current_ver = self.db.get_current_version(self.encounter_id)
        event = Event(
            event_id=self.id_factory.next_id("ev"),
            encounter_id=self.encounter_id,
            sequence=current_ver + 1,
            at=now_iso,
            actor=self.actor,
            type=ev_type,
            target=finding_id,
            payload=updated_finding.model_dump(mode="json"),
            before={"confirmation": existing.confirmation.model_dump(mode="json")},
            after={"confirmation": updated_finding.confirmation.model_dump(mode="json")},
        )
        self.db.append_event(event, expected_version=expected_version)
        return updated_finding

    def add_hypothesis(self, hypothesis: Hypothesis, expected_version: Optional[int] = None) -> Hypothesis:
        """Add a candidate diagnosis to the Case Graph.

        Permissions:
        - proposer (LLM) may only add hypothesis with origin containing LLM
        - kb_lookup / mnm may only add hypothesis with origin containing KB or MNM
        """
        if hypothesis.encounter_id != self.encounter_id:
            raise ValueError(
                f"Hypothesis encounter_id '{hypothesis.encounter_id}' does not match client encounter '{self.encounter_id}'"
            )

        if self.component in {"proposer", "llm_proposer"}:
            if HypothesisOrigin.LLM not in hypothesis.origin:
                raise PermissionDenied(
                    self.component, "add_hypothesis", "Proposer can only add hypotheses with origin=LLM"
                )
        elif self.component in {"kb_lookup", "mnm"}:
            valid_origins = {HypothesisOrigin.KB, HypothesisOrigin.MNM}
            if not any(o in valid_origins for o in hypothesis.origin):
                raise PermissionDenied(
                    self.component, "add_hypothesis", "KB lookup can only add hypotheses with origin=KB or MNM"
                )
        elif self.component not in {"orchestrator", "test"}:
            raise PermissionDenied(self.component, "add_hypothesis")

        # Schema validation
        _validate_schema("hypothesis", hypothesis)

        current_view = self.view()
        if current_view.hypothesis_by_id(hypothesis.id) is not None:
            raise ValueError(f"Hypothesis '{hypothesis.id}' already exists in encounter '{self.encounter_id}'.")

        current_ver = self.db.get_current_version(self.encounter_id)
        event = Event(
            event_id=self.id_factory.next_id("ev"),
            encounter_id=self.encounter_id,
            sequence=current_ver + 1,
            at=self.clock.now_iso(),
            actor=self.actor,
            type=EventType.HYPOTHESIS_ADDED.value,
            target=hypothesis.id,
            payload=hypothesis.model_dump(mode="json"),
            round=hypothesis.round,
        )
        self.db.append_event(event, expected_version=expected_version)
        return hypothesis

    def add_claim(self, claim: Claim, expected_version: Optional[int] = None) -> Claim:
        """Add a proposed claim.

        Permissions: proposer (LLM), kb_lookup, or test.
        """
        allowed = {"proposer", "llm_proposer", "kb_lookup", "orchestrator", "test"}
        if self.component not in allowed:
            raise PermissionDenied(self.component, "add_claim")

        if claim.encounter_id != self.encounter_id:
            raise ValueError(
                f"Claim encounter_id '{claim.encounter_id}' does not match client encounter '{self.encounter_id}'"
            )

        # Schema validation
        _validate_schema("claim", claim)

        current_ver = self.db.get_current_version(self.encounter_id)
        event = Event(
            event_id=self.id_factory.next_id("ev"),
            encounter_id=self.encounter_id,
            sequence=current_ver + 1,
            at=self.clock.now_iso(),
            actor=self.actor,
            type=EventType.CLAIM_ADDED.value,
            target=claim.claim_id,
            payload=claim.model_dump(mode="json"),
            round=claim.round,
        )
        self.db.append_event(event, expected_version=expected_version)
        return claim

    def add_verdict(self, verdict: Verdict, expected_version: Optional[int] = None) -> Verdict:
        """Add a verifier check result.

        Permissions: verifiers, verifier, or test.
        """
        allowed = {"verifier", "verifiers", "citation_judge", "lab_interpreter", "rule_checker", "orchestrator", "test"}
        if self.component not in allowed:
            raise PermissionDenied(self.component, "add_verdict")

        # Schema validation
        _validate_schema("verdict", verdict)

        current_ver = self.db.get_current_version(self.encounter_id)
        event = Event(
            event_id=self.id_factory.next_id("ev"),
            encounter_id=self.encounter_id,
            sequence=current_ver + 1,
            at=self.clock.now_iso(),
            actor=self.actor,
            type=EventType.VERDICT_ADDED.value,
            target=verdict.verdict_id,
            payload=verdict.model_dump(mode="json"),
        )
        self.db.append_event(event, expected_version=expected_version)
        return verdict

    def update_scores(
        self,
        hypothesis_id: str,
        prior: Optional[float],
        p_raw: Optional[float],
        p_calibrated: Optional[float],
        band: Optional[Band],
        lr_trail: List[Any],
        because: List[str],
        expected_version: Optional[int] = None,
    ) -> Hypothesis:
        """Update scores on a hypothesis.

        Permissions: scorer or test.
        """
        allowed = {"scorer", "test"}
        if self.component not in allowed:
            raise PermissionDenied(self.component, "update_scores")

        current_view = self.view()
        existing = current_view.hypothesis_by_id(hypothesis_id)
        if existing is None:
            raise ValueError(f"Hypothesis '{hypothesis_id}' not found in encounter '{self.encounter_id}'.")

        updated_hyp = existing.model_copy(
            update={
                "prior": prior,
                "p_raw": p_raw,
                "p_calibrated": p_calibrated,
                "band": band,
                "lr_trail": lr_trail,
            }
        )
        _validate_schema("hypothesis", updated_hyp)

        current_ver = self.db.get_current_version(self.encounter_id)
        event = Event(
            event_id=self.id_factory.next_id("ev"),
            encounter_id=self.encounter_id,
            sequence=current_ver + 1,
            at=self.clock.now_iso(),
            actor=self.actor,
            type=EventType.HYPOTHESIS_RESCORED.value,
            target=hypothesis_id,
            payload=updated_hyp.model_dump(mode="json"),
            before={"prior": existing.prior, "p_raw": existing.p_raw, "p_calibrated": existing.p_calibrated},
            after={"prior": prior, "p_raw": p_raw, "p_calibrated": p_calibrated},
            because=because,
            round=existing.round,
        )
        self.db.append_event(event, expected_version=expected_version)
        return updated_hyp

    def set_hypothesis_status(
        self,
        hypothesis_id: str,
        status: str,
        reason: str,
        expected_version: Optional[int] = None,
    ) -> Hypothesis:
        """Set candidate status (active, ruled_out, confirmed_by_clinician, rejected_by_clinician).

        Permissions: clinician, checkpoint_2, or test.
        """
        allowed = {"clinician", "checkpoint_2", "orchestrator", "test"}
        if self.component not in allowed:
            raise PermissionDenied(self.component, "set_hypothesis_status")

        try:
            status_enum = HypothesisStatus(status)
        except ValueError:
            raise ValueError(f"Invalid hypothesis status '{status}'")

        current_view = self.view()
        existing = current_view.hypothesis_by_id(hypothesis_id)
        if existing is None:
            raise ValueError(f"Hypothesis '{hypothesis_id}' not found in encounter '{self.encounter_id}'.")

        ruled_out_by = reason if status_enum == HypothesisStatus.RULED_OUT else existing.ruled_out_by
        updated_hyp = existing.model_copy(
            update={"status": status_enum, "ruled_out_by": ruled_out_by}
        )
        _validate_schema("hypothesis", updated_hyp)

        current_ver = self.db.get_current_version(self.encounter_id)
        event = Event(
            event_id=self.id_factory.next_id("ev"),
            encounter_id=self.encounter_id,
            sequence=current_ver + 1,
            at=self.clock.now_iso(),
            actor=self.actor,
            type=EventType.HYPOTHESIS_STATUS_CHANGED.value,
            target=hypothesis_id,
            payload=updated_hyp.model_dump(mode="json"),
            before={"status": existing.status.value},
            after={"status": status_enum.value, "reason": reason},
        )
        self.db.append_event(event, expected_version=expected_version)
        return updated_hyp

    def add_edge(
        self,
        edge_type: str,
        src: str,
        dst: str,
        data: Optional[dict[str, Any]] = None,
        expected_version: Optional[int] = None,
    ) -> Edge:
        """Add a graph edge.

        Permissions:
        - Ingestion may write 'contradicts' or 'derived_from'
        - Planner may write 'discriminates', 'rules_out', 'recommends'
        - Verifiers may write 'verified_by'
        """
        allowed_types = {
            "supports", "refutes", "contradicts", "derived_from",
            "discriminates", "verified_by", "rules_out", "recommends",
        }
        if edge_type not in allowed_types:
            raise ValueError(f"Invalid edge_type '{edge_type}'. Allowed: {allowed_types}")

        if self.component == "ingestion" and edge_type not in {"contradicts", "derived_from"}:
            raise PermissionDenied(self.component, "add_edge", f"Ingestion cannot write edge_type '{edge_type}'")
        elif self.component == "planner" and edge_type not in {"discriminates", "rules_out", "recommends"}:
            raise PermissionDenied(self.component, "add_edge", f"Planner cannot write edge_type '{edge_type}'")

        # Validate that src and dst nodes exist in the current Case Graph view
        # (derived_from dst may be an external source record, but src must be a finding)
        current_view = self.view()
        if not current_view.has_node(src):
            raise ValueError(
                f"Source node '{src}' does not exist in encounter '{self.encounter_id}'."
            )
        if edge_type != "derived_from" and not current_view.has_node(dst):
            raise ValueError(
                f"Destination node '{dst}' does not exist in encounter '{self.encounter_id}'."
            )

        edge_id = self.id_factory.next_id("edge")
        edge = Edge(
            id=edge_id,
            encounter_id=self.encounter_id,
            type=edge_type,
            src=src,
            dst=dst,
            data=data,
            version=1,
        )

        current_ver = self.db.get_current_version(self.encounter_id)
        event = Event(
            event_id=self.id_factory.next_id("ev"),
            encounter_id=self.encounter_id,
            sequence=current_ver + 1,
            at=self.clock.now_iso(),
            actor=self.actor,
            type=EventType.EDGE_ADDED.value,
            target=edge.id,
            payload=edge.model_dump(mode="json"),
        )
        self.db.append_event(event, expected_version=expected_version)
        return edge
