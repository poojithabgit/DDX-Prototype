"""
src/graph/events.py

Event types and event validation for the Case Graph append-only log.

Follows docs/04-case-graph.md section 4:
Nothing is updated in place. Every change is an immutable Event.
"""

from enum import Enum


class EventType(str, Enum):
    """Catalog of event types for the Case Graph audit trail."""
    CONTEXT_SET = "CONTEXT_SET"
    FINDING_ADDED = "FINDING_ADDED"
    FINDING_CONFIRMED = "FINDING_CONFIRMED"
    FINDING_REJECTED = "FINDING_REJECTED"
    FINDING_EDITED = "FINDING_EDITED"
    HYPOTHESIS_ADDED = "HYPOTHESIS_ADDED"
    HYPOTHESIS_STATUS_CHANGED = "HYPOTHESIS_STATUS_CHANGED"
    HYPOTHESIS_RESCORED = "HYPOTHESIS_RESCORED"
    CLAIM_ADDED = "CLAIM_ADDED"
    VERDICT_ADDED = "VERDICT_ADDED"
    EDGE_ADDED = "EDGE_ADDED"
