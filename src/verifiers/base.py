"""
src/verifiers/base.py

Verifier Protocol and Base Interface.
Follows docs/INTERFACES.md section 8.2 and docs/08-verification.md section 1:

class Verifier(Protocol):
    name: str                         # e.g. "kb-link-checker"
    version: str                      # e.g. "0.2.0"
    deterministic: bool
    handles: frozenset[ClaimType]

    def verify(self, claim: Claim, view: CaseView, kb: KB) -> Verdict: ...

Safety Rules:
- A claim type not in handles returns NOT_APPLICABLE.
- A tool or resource failure returns UNVERIFIABLE with unverifiable_reason="tool_unavailable". It does not raise.
- SUPPORT or REFUTE always includes kb_entry, rule_id, or citation.
- Never promotes trust tiers or modifies graph data directly.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from src.common.models import Claim, Verdict
from src.common.types import ClaimType
from src.graph.view import CaseView
from src.reasoning.kb import KB


@runtime_checkable
class Verifier(Protocol):
    """Protocol for all Medagents claim verifiers."""
    name: str
    version: str
    deterministic: bool
    handles: frozenset[ClaimType]

    def verify(self, claim: Claim, view: CaseView, kb: KB) -> Verdict:
        """Verify one claim against the CaseView and KB, returning a Verdict."""
        ...
