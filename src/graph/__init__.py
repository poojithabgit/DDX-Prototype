"""
src/graph/__init__.py

Case Graph package export.
Provides:
- EventStore: In-memory append-only event store partitioned by encounter_id
- GraphClient: Scoped component client enforcing permissions and schema constraints
- CaseView: Immutable point-in-time case state snapshot
- EventType: Event taxonomy for the audit log
"""

from src.graph.events import EventType
from src.graph.view import CaseView
from src.graph.store import EventStore
from src.graph.client import GraphClient

__all__ = [
    "EventType",
    "CaseView",
    "EventStore",
    "GraphClient",
]
