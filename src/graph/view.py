"""
src/graph/view.py

Immutable snapshot of the Case Graph for one patient encounter.
Maps directly to CaseView in docs/INTERFACES.md section 3:

class CaseView:
    encounter_id: str
    version: int
    context: PatientContext
    findings: list[Finding]
    hypotheses: list[Hypothesis]
    claims: list[Claim]
    verdicts: list[Verdict]
    edges: list[Edge]

    def confirmed_findings(self) -> list[Finding]: ...
    def verdict_for(self, claim_id: str) -> Verdict | None: ...
    def top_hypotheses(self, k: int = 5) -> list[Hypothesis]: ...
"""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field

from src.common.models import (
    Claim,
    Edge,
    Finding,
    Hypothesis,
    PatientContext,
    Verdict,
)
from src.common.types import TrustTier


class CaseView(BaseModel):
    """Immutable snapshot of the Case Graph at a specific version point."""
    model_config = {"frozen": True}

    encounter_id: str
    version: int = Field(..., ge=0, description="Number of events applied to reach this view")
    context: Optional[PatientContext] = None
    findings: List[Finding] = Field(default_factory=list)
    hypotheses: List[Hypothesis] = Field(default_factory=list)
    claims: List[Claim] = Field(default_factory=list)
    verdicts: List[Verdict] = Field(default_factory=list)
    edges: List[Edge] = Field(default_factory=list)

    def confirmed_findings(self) -> List[Finding]:
        """Return findings at tiers T1 to T5 that are confirmed.

        Per docs/04-case-graph.md section 3 & INTERFACES.md:
        T6 findings are NEVER included here, even if clinician marked them,
        unless promoted through explicit verified workflow (and by default T6 cannot move scores).
        Only confirmed findings can move scores.
        """
        return [
            f for f in self.findings
            if f.trust_tier in {
                TrustTier.T1,
                TrustTier.T2,
                TrustTier.T3,
                TrustTier.T4,
                TrustTier.T5,
            } and f.is_confirmed()
        ]

    def finding_by_id(self, finding_id: str) -> Optional[Finding]:
        """Lookup a finding by ID."""
        for f in self.findings:
            if f.id == finding_id:
                return f
        return None

    def hypothesis_by_id(self, hypothesis_id: str) -> Optional[Hypothesis]:
        """Lookup a hypothesis by ID."""
        for h in self.hypotheses:
            if h.id == hypothesis_id:
                return h
        return None

    def claim_by_id(self, claim_id: str) -> Optional[Claim]:
        """Lookup a claim by ID."""
        for c in self.claims:
            if c.claim_id == claim_id:
                return c
        return None

    def verdict_by_id(self, verdict_id: str) -> Optional[Verdict]:
        """Lookup a verdict by ID."""
        for v in self.verdicts:
            if v.verdict_id == verdict_id:
                return v
        return None

    def has_node(self, node_id: str) -> bool:
        """Check whether a node ID exists in this view (finding, hypothesis, claim, or verdict)."""
        if self.finding_by_id(node_id) is not None:
            return True
        if self.hypothesis_by_id(node_id) is not None:
            return True
        if self.claim_by_id(node_id) is not None:
            return True
        if self.verdict_by_id(node_id) is not None:
            return True
        return False

    def verdict_for(self, claim_id: str) -> Optional[Verdict]:
        """Return the verdict for a given claim_id, or None if unverified."""
        for v in self.verdicts:
            if v.claim_id == claim_id:
                return v
        return None

    def top_hypotheses(self, k: int = 5) -> List[Hypothesis]:
        """Return top k hypotheses ranked by p_calibrated (or p_raw if uncalibrated)."""
        def sort_key(h: Hypothesis) -> float:
            if h.p_calibrated is not None:
                return h.p_calibrated
            if h.p_raw is not None:
                return h.p_raw
            if h.prior is not None:
                return h.prior
            return -1.0

        return sorted(self.hypotheses, key=sort_key, reverse=True)[:k]
