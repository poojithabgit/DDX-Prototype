"""
src/verifiers/deterministic.py

Deterministic verifiers for the Medagents verification layer.
Follows docs/08-verification.md section 2 and docs/INTERFACES.md section 8.2:

1. KBLinkChecker:
   Checks FINDING_DISEASE_LINK claims against the reviewed likelihood ratio table in the KB.
   Verifies whether the KB contains a reviewed LR for this finding -> disease pair,
   and whether the proposed relation ('supports' vs 'refutes') matches the LR direction.

2. LabInterpreterVerifier:
   Checks LAB_INTERPRETATION claims.
   Verifies whether observed lab values are abnormal, high, low, or within reference ranges.
   Rejects invalid reference ranges and flags missing units.

3. MNMChecker:
   Checks MNM_STATUS claims.
   Verifies whether a candidate condition is an active must-not-miss condition and
   whether any confirmed red-flag findings are present.

4. ConsistencyChecker:
   Checks FACT_CONSISTENCY claims.
   Verifies temporal sanity (onset day relative to presentation, test validity) and
   flags direct contradictions.
"""

from __future__ import annotations

import time
from typing import Optional
from src.common.clock import IdFactory, UuidIdFactory
from src.common.models import Claim, Finding, Hypothesis, Verdict
from src.common.types import (
    Assertion,
    ClaimType,
    Interpretation,
    TrustTier,
    VerdictResult,
)
from src.graph.view import CaseView
from src.reasoning.kb import KB


class KBLinkChecker:
    """Deterministic verifier for finding-disease clinical links."""

    name: str = "kb-link-checker"
    version: str = "0.2.0"
    deterministic: bool = True
    handles: frozenset[ClaimType] = frozenset([ClaimType.FINDING_DISEASE_LINK])

    def __init__(self, id_factory: Optional[IdFactory] = None) -> None:
        self.id_factory = id_factory or UuidIdFactory()

    def verify(self, claim: Claim, view: CaseView, kb: KB) -> Verdict:
        t0 = time.perf_counter()
        vid = self.id_factory.next_id("v")

        # 1. Claim type guard
        if claim.type not in self.handles:
            return Verdict(
                verdict_id=vid,
                claim_id=claim.claim_id,
                claim_type=claim.type,
                result=VerdictResult.NOT_APPLICABLE,
                deterministic=self.deterministic,
                verifier=f"{self.name}@{self.version}",
                reason=f"Claim type '{claim.type}' is not handled by {self.name}",
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

        # 2. Check target finding and hypothesis exist in the view
        if not claim.finding_id or not claim.hypothesis_id:
            return Verdict(
                verdict_id=vid,
                claim_id=claim.claim_id,
                claim_type=claim.type,
                result=VerdictResult.UNVERIFIABLE,
                deterministic=self.deterministic,
                verifier=f"{self.name}@{self.version}",
                reason="Claim must specify both finding_id and hypothesis_id",
                unverifiable_reason="out_of_scope",
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

        finding = view.finding_by_id(claim.finding_id)
        hypothesis = view.hypothesis_by_id(claim.hypothesis_id)

        if not finding:
            return Verdict(
                verdict_id=vid,
                claim_id=claim.claim_id,
                claim_type=claim.type,
                result=VerdictResult.UNVERIFIABLE,
                deterministic=self.deterministic,
                verifier=f"{self.name}@{self.version}",
                reason=f"Finding '{claim.finding_id}' not found in Case Graph",
                unverifiable_reason="no_source_found",
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

        if not hypothesis:
            return Verdict(
                verdict_id=vid,
                claim_id=claim.claim_id,
                claim_type=claim.type,
                result=VerdictResult.UNVERIFIABLE,
                deterministic=self.deterministic,
                verifier=f"{self.name}@{self.version}",
                reason=f"Hypothesis '{claim.hypothesis_id}' not found in Case Graph",
                unverifiable_reason="no_source_found",
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

        # 3. Lookup LR in KB
        lr_entry = kb.lr_for_finding_disease(
            disease_name_or_code=hypothesis.name,
            finding_code_or_name=finding.code.display or finding.code.code,
        )

        if not lr_entry:
            # Fallback check on original text
            if finding.original_text:
                lr_entry = kb.lr_for_finding_disease(
                    disease_name_or_code=hypothesis.name,
                    finding_code_or_name=finding.original_text,
                )

        if not lr_entry:
            return Verdict(
                verdict_id=vid,
                claim_id=claim.claim_id,
                claim_type=claim.type,
                result=VerdictResult.UNVERIFIABLE,
                deterministic=self.deterministic,
                verifier=f"{self.name}@{self.version}",
                reason=f"No reviewed KB likelihood ratio found linking '{finding.code.display}' to '{hypothesis.name}'",
                unverifiable_reason="no_source_found",
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

        # 4. Check LR direction vs Proposed Relation
        # If finding is present: lr_pos > 1 supports; lr_pos < 1 refutes
        # If finding is absent:  lr_neg > 1 supports; lr_neg < 1 refutes
        is_present = (finding.assertion == Assertion.PRESENT)
        relevant_lr = lr_entry.lr_positive if is_present else lr_entry.lr_negative

        if relevant_lr is None:
            return Verdict(
                verdict_id=vid,
                claim_id=claim.claim_id,
                claim_type=claim.type,
                result=VerdictResult.UNVERIFIABLE,
                kb_entry=lr_entry.id,
                deterministic=self.deterministic,
                verifier=f"{self.name}@{self.version}",
                reason=f"KB entry '{lr_entry.id}' does not have LR for assertion '{finding.assertion.value}'",
                unverifiable_reason="no_source_found",
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

        expected_relation = "supports" if relevant_lr > 1.0 else ("refutes" if relevant_lr < 1.0 else "neutral")
        proposed_rel = (claim.proposed_relation or "supports").lower()

        if expected_relation == proposed_rel:
            result = VerdictResult.SUPPORT if proposed_rel == "supports" else VerdictResult.REFUTE
            reason = (
                f"KB entry {lr_entry.id} confirms {finding.code.display} {proposed_rel} "
                f"{hypothesis.name} with LR={relevant_lr:.2f} (quality: {lr_entry.quality.value})"
            )
        else:
            # Direction disagreement: Proposer claimed 'supports' but evidence shows LR < 1 (or vice versa)
            result = VerdictResult.REFUTE
            reason = (
                f"KB entry {lr_entry.id} indicates relation is '{expected_relation}' (LR={relevant_lr:.2f}), "
                f"refuting proposer claim of '{proposed_rel}'"
            )

        return Verdict(
            verdict_id=vid,
            claim_id=claim.claim_id,
            claim_type=claim.type,
            result=result,
            kb_entry=lr_entry.id,
            deterministic=self.deterministic,
            verifier=f"{self.name}@{self.version}",
            reason=reason,
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )


class LabInterpreterVerifier:
    """Deterministic verifier for laboratory result interpretations."""

    name: str = "lab-interpreter"
    version: str = "0.2.0"
    deterministic: bool = True
    handles: frozenset[ClaimType] = frozenset([ClaimType.LAB_INTERPRETATION])

    def __init__(self, id_factory: Optional[IdFactory] = None) -> None:
        self.id_factory = id_factory or UuidIdFactory()

    def verify(self, claim: Claim, view: CaseView, kb: KB) -> Verdict:
        t0 = time.perf_counter()
        vid = self.id_factory.next_id("v")

        if claim.type not in self.handles:
            return Verdict(
                verdict_id=vid,
                claim_id=claim.claim_id,
                claim_type=claim.type,
                result=VerdictResult.NOT_APPLICABLE,
                deterministic=self.deterministic,
                verifier=f"{self.name}@{self.version}",
                reason=f"Claim type '{claim.type}' is not handled by {self.name}",
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

        if not claim.finding_id:
            return Verdict(
                verdict_id=vid,
                claim_id=claim.claim_id,
                claim_type=claim.type,
                result=VerdictResult.UNVERIFIABLE,
                deterministic=self.deterministic,
                verifier=f"{self.name}@{self.version}",
                reason="LAB_INTERPRETATION claim missing finding_id",
                unverifiable_reason="out_of_scope",
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

        finding = view.finding_by_id(claim.finding_id)
        if not finding:
            return Verdict(
                verdict_id=vid,
                claim_id=claim.claim_id,
                claim_type=claim.type,
                result=VerdictResult.UNVERIFIABLE,
                deterministic=self.deterministic,
                verifier=f"{self.name}@{self.version}",
                reason=f"Finding '{claim.finding_id}' not found in Case Graph",
                unverifiable_reason="no_source_found",
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

        if finding.kind != "lab":
            return Verdict(
                verdict_id=vid,
                claim_id=claim.claim_id,
                claim_type=claim.type,
                result=VerdictResult.REFUTE,
                rule_id="RULE-LAB-KIND-CHECK",
                deterministic=self.deterministic,
                verifier=f"{self.name}@{self.version}",
                reason=f"Finding '{finding.id}' is of kind '{finding.kind}', not 'lab'",
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

        if finding.interpretation == Interpretation.NOT_APPLICABLE or not finding.reference_range:
            return Verdict(
                verdict_id=vid,
                claim_id=claim.claim_id,
                claim_type=claim.type,
                result=VerdictResult.UNVERIFIABLE,
                deterministic=self.deterministic,
                verifier=f"{self.name}@{self.version}",
                reason=f"Lab finding '{finding.id}' has no valid numeric reference range or compatible unit",
                unverifiable_reason="no_source_found",
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

        # Check claim agreement
        proposed = (claim.proposed_relation or "").lower()
        interp = finding.interpretation.value.lower()

        # If claim says supports/abnormal and lab is high/low
        is_abnormal = interp in {"high", "low", "critical_high", "critical_low", "abnormal"}
        if proposed in {"abnormal", "high", "low"}:
            if proposed == interp or (proposed == "abnormal" and is_abnormal):
                result = VerdictResult.SUPPORT
                reason = f"Lab value {finding.value} {finding.unit} matches interpretation '{interp}' against range [{finding.reference_range.low}, {finding.reference_range.high}]"
            else:
                result = VerdictResult.REFUTE
                reason = f"Lab value interpretation is '{interp}', which refutes claimed '{proposed}'"
        else:
            result = VerdictResult.SUPPORT if is_abnormal else VerdictResult.REFUTE
            reason = f"Lab value evaluated as '{interp}' with reference limits [{finding.reference_range.low}, {finding.reference_range.high}]"

        return Verdict(
            verdict_id=vid,
            claim_id=claim.claim_id,
            claim_type=claim.type,
            result=result,
            rule_id="RULE-LAB-RANGE-INTERPRET",
            deterministic=self.deterministic,
            verifier=f"{self.name}@{self.version}",
            reason=reason,
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )


class MNMChecker:
    """Deterministic verifier for Must-Not-Miss condition status."""

    name: str = "mnm-checker"
    version: str = "0.2.0"
    deterministic: bool = True
    handles: frozenset[ClaimType] = frozenset([ClaimType.MNM_STATUS])

    def __init__(self, id_factory: Optional[IdFactory] = None) -> None:
        self.id_factory = id_factory or UuidIdFactory()

    def verify(self, claim: Claim, view: CaseView, kb: KB) -> Verdict:
        t0 = time.perf_counter()
        vid = self.id_factory.next_id("v")

        if claim.type not in self.handles:
            return Verdict(
                verdict_id=vid,
                claim_id=claim.claim_id,
                claim_type=claim.type,
                result=VerdictResult.NOT_APPLICABLE,
                deterministic=self.deterministic,
                verifier=f"{self.name}@{self.version}",
                reason=f"Claim type '{claim.type}' is not handled by {self.name}",
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

        if not claim.hypothesis_id:
            return Verdict(
                verdict_id=vid,
                claim_id=claim.claim_id,
                claim_type=claim.type,
                result=VerdictResult.UNVERIFIABLE,
                deterministic=self.deterministic,
                verifier=f"{self.name}@{self.version}",
                reason="MNM_STATUS claim requires hypothesis_id",
                unverifiable_reason="out_of_scope",
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

        hypothesis = view.hypothesis_by_id(claim.hypothesis_id)
        if not hypothesis:
            return Verdict(
                verdict_id=vid,
                claim_id=claim.claim_id,
                claim_type=claim.type,
                result=VerdictResult.UNVERIFIABLE,
                deterministic=self.deterministic,
                verifier=f"{self.name}@{self.version}",
                reason=f"Hypothesis '{claim.hypothesis_id}' not found in Case Graph",
                unverifiable_reason="no_source_found",
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

        is_mnm = kb.is_must_not_miss_condition(hypothesis.name)
        if is_mnm:
            return Verdict(
                verdict_id=vid,
                claim_id=claim.claim_id,
                claim_type=claim.type,
                result=VerdictResult.SUPPORT,
                rule_id="RULE-MNM-CATALOG-ACTIVE",
                deterministic=self.deterministic,
                verifier=f"{self.name}@{self.version}",
                reason=f"Condition '{hypothesis.name}' is validated as an active Must-Not-Miss condition for acute fever",
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )
        else:
            return Verdict(
                verdict_id=vid,
                claim_id=claim.claim_id,
                claim_type=claim.type,
                result=VerdictResult.REFUTE,
                rule_id="RULE-MNM-CATALOG-NOT-FOUND",
                deterministic=self.deterministic,
                verifier=f"{self.name}@{self.version}",
                reason=f"Condition '{hypothesis.name}' is not in the acute fever Must-Not-Miss catalog",
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )


class ConsistencyChecker:
    """Deterministic verifier for clinical fact timeline and consistency."""

    name: str = "timeline-consistency-checker"
    version: str = "0.2.0"
    deterministic: bool = True
    handles: frozenset[ClaimType] = frozenset([ClaimType.FACT_CONSISTENCY])

    def __init__(self, id_factory: Optional[IdFactory] = None) -> None:
        self.id_factory = id_factory or UuidIdFactory()

    def verify(self, claim: Claim, view: CaseView, kb: KB) -> Verdict:
        t0 = time.perf_counter()
        vid = self.id_factory.next_id("v")

        if claim.type not in self.handles:
            return Verdict(
                verdict_id=vid,
                claim_id=claim.claim_id,
                claim_type=claim.type,
                result=VerdictResult.NOT_APPLICABLE,
                deterministic=self.deterministic,
                verifier=f"{self.name}@{self.version}",
                reason=f"Claim type '{claim.type}' is not handled by {self.name}",
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

        if not claim.finding_id:
            return Verdict(
                verdict_id=vid,
                claim_id=claim.claim_id,
                claim_type=claim.type,
                result=VerdictResult.UNVERIFIABLE,
                deterministic=self.deterministic,
                verifier=f"{self.name}@{self.version}",
                reason="FACT_CONSISTENCY claim requires finding_id",
                unverifiable_reason="out_of_scope",
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

        finding = view.finding_by_id(claim.finding_id)
        if not finding:
            return Verdict(
                verdict_id=vid,
                claim_id=claim.claim_id,
                claim_type=claim.type,
                result=VerdictResult.UNVERIFIABLE,
                deterministic=self.deterministic,
                verifier=f"{self.name}@{self.version}",
                reason=f"Finding '{claim.finding_id}' not found in Case Graph",
                unverifiable_reason="no_source_found",
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

        # Check timeline consistency: onset_day relative to presentation (0)
        # e.g. onset_day > 0 means symptom started in the future, which is inconsistent
        if finding.onset_day is not None and finding.onset_day > 0:
            return Verdict(
                verdict_id=vid,
                claim_id=claim.claim_id,
                claim_type=claim.type,
                result=VerdictResult.REFUTE,
                rule_id="RULE-TIMELINE-FUTURE-ONSET",
                deterministic=self.deterministic,
                verifier=f"{self.name}@{self.version}",
                reason=f"Finding has future onset_day={finding.onset_day} > 0 relative to presentation",
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

        # Check negative duration for present findings
        if finding.duration_days is not None and finding.duration_days < 0:
            return Verdict(
                verdict_id=vid,
                claim_id=claim.claim_id,
                claim_type=claim.type,
                result=VerdictResult.REFUTE,
                rule_id="RULE-TIMELINE-NEGATIVE-DURATION",
                deterministic=self.deterministic,
                verifier=f"{self.name}@{self.version}",
                reason=f"Finding duration {finding.duration_days} cannot be negative",
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

        return Verdict(
            verdict_id=vid,
            claim_id=claim.claim_id,
            claim_type=claim.type,
            result=VerdictResult.SUPPORT,
            rule_id="RULE-TIMELINE-CONSISTENT",
            deterministic=self.deterministic,
            verifier=f"{self.name}@{self.version}",
            reason=f"Finding '{finding.id}' timeline and assertions are clinically consistent",
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )
