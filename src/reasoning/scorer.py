"""
src/reasoning/scorer.py

Deterministic Bayesian scoring engine for diagnostic hypotheses.
Follows docs/07-reasoning-and-scoring.md section B and docs/INTERFACES.md section 8.4:

Key clinical safety and architecture rules:
1. Prior matching:
   Retrieves prior from KB matching patient context or hypothesis.prior.
   Hypotheses without a prior cannot be scored (returned as unscored).
2. Evidence filtering (docs/07-reasoning-and-scoring.md section B2):
   An LR enters the formula ONLY if ALL three are true:
   - The finding is confirmed (trust tier T1 to T5, is_confirmed == True).
   - Unconfirmed T6 findings NEVER move scores (LR = 1.0).
   - The finding-hypothesis link has a verified verdict of SUPPORT or REFUTE.
   - The KB has a reviewed LR entry for that finding and disease.
3. Direction agreement check:
   SUPPORT must agree with LR > 1.0; REFUTE must agree with LR < 1.0.
   If direction disagrees, use LR = 1.0 and flag the KB entry for clinical review.
   If LR = 1.0 (neutral evidence), it leaves the score unchanged (log(1.0) = 0).
4. Correlated findings grouping (docs/07-reasoning-and-scoring.md section B3):
   Findings in the same KB finding_group are not multiplied naively.
   If a combined LR exists, it is used; otherwise, the single strongest LR in the group is used.
5. Expert opinion clipping (docs/07-reasoning-and-scoring.md section B4):
   LRs with quality='expert-opinion' are clipped to [0.5, 2.0].
6. Probability bands (docs/07-reasoning-and-scoring.md section B6):
   HIGH >= 0.50, MODERATE 0.20-0.49, LOW 0.05-0.19, VERY_LOW < 0.05.
7. Must-Not-Miss visibility:
   MNM conditions remain independently visible and flagged, regardless of posterior probability score.
8. Full audit trail:
   Preserves complete provenance including finding_or_group, applied LR, kb_entry ID, verdict_id.
"""

from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from src.common.models import (
    Finding,
    Hypothesis,
    LRTrailEntry,
    Verdict,
)
from src.common.types import (
    Assertion,
    Band,
    LRQuality,
    TrustTier,
    VerdictResult,
)
from src.graph.view import CaseView
from src.reasoning.bayes import (
    log_odds_to_prob,
    prob_to_log_odds,
)
from src.reasoning.kb import KB

logger = logging.getLogger(__name__)


class ScoreResult(BaseModel):
    """Result of scoring one diagnostic hypothesis."""
    model_config = {"extra": "forbid"}

    hypothesis_id: str
    hypothesis_name: str
    must_not_miss: bool
    prior: float
    p_raw: float
    p_calibrated: float
    band: Band
    lr_trail: List[LRTrailEntry] = Field(default_factory=list)
    flagged_kb_entries: List[str] = Field(default_factory=list)
    unscored_reason: Optional[str] = None


def assign_band(prob: float) -> Band:
    """Assign unvalidated demonstration probability band based on calibrated posterior.

    RESEARCH & PROTOTYPE DEMONSTRATION NOTICE:
    These bands (HIGH, MODERATE, LOW, VERY_LOW) are unvalidated demonstration bands
    for algorithm testing and interface development. They are NOT clinical risk classifications
    and must NEVER be used for clinical triage, risk assessment, or decision-making.

    Follows docs/07-reasoning-and-scoring.md section B6:
    - High: >= 0.50
    - Moderate: 0.20 to 0.49
    - Low: 0.05 to 0.19
    - Very Low: < 0.05
    """
    if prob >= 0.50:
        return Band.HIGH
    elif prob >= 0.20:
        return Band.MODERATE
    elif prob >= 0.05:
        return Band.LOW
    else:
        return Band.VERY_LOW


def clip_if_expert_opinion(lr: float, quality: LRQuality) -> float:
    """Clip weak expert-opinion likelihood ratios to [0.5, 2.0] per docs/07 B4."""
    if quality == LRQuality.EXPERT_OPINION:
        return max(0.5, min(lr, 2.0))
    return lr


def score_hypothesis(
    hypothesis: Hypothesis,
    view: CaseView,
    kb: KB,
) -> Optional[ScoreResult]:
    """Score a single candidate hypothesis against verified findings in the CaseView.

    Returns ScoreResult, or None if the hypothesis cannot be scored (no prior).
    """
    # 1. Determine prior probability
    prior = hypothesis.prior
    if prior is None:
        # Check priors table in KB
        prior = kb.priors_table.get(hypothesis.name)

    if prior is None:
        logger.info("Hypothesis '%s' has no KB prior; unscored.", hypothesis.name)
        return None

    if prior <= 0.0 or prior >= 1.0:
        raise ValueError(f"Invalid prior probability {prior} for hypothesis '{hypothesis.name}'")

    current_log_odds = prob_to_log_odds(prior)
    lr_trail: List[LRTrailEntry] = []
    flagged_kb_entries: List[str] = []

    # 2. Gather eligible findings
    # CRITICAL SAFETY GATES:
    # 1. Only confirmed findings in tiers T1-T5 can move scores.
    #    Unconfirmed T6 findings are strictly filtered out by view.confirmed_findings()!
    # 2. Synthetic provenance exclusion:
    #    Findings originating from synthetic unvalidated datasets (e.g. synthetic extractor,
    #    synthetic_unvalidated review status, or synthetic source_ids) must NEVER influence
    #    diagnostic scores, even if manually given tier T1 or confirmed by a clinician.
    confirmed_findings = view.confirmed_findings()
    eligible_findings: List[Finding] = []

    for f in confirmed_findings:
        # Strict synthetic provenance filter
        src_id = (f.provenance.source_id or "").lower()
        extractor = (f.provenance.extractor or "").lower()
        quote = (f.provenance.quote or "").lower()

        is_synthetic = (
            "synthetic" in src_id or
            "synthetic" in extractor or
            "prototype-extractor" in extractor or
            "synthetic_label" in src_id or
            "synthetic_unvalidated" in src_id
        )

        if not is_synthetic:
            eligible_findings.append(f)
        else:
            logger.debug(
                "Finding '%s' excluded from Bayesian scoring: synthetic provenance detected (%s, %s).",
                f.id, src_id, extractor
            )

    # Pre-organize findings by finding_group for correlated findings handling (docs/07 B3)
    grouped_findings: Dict[str, List[Finding]] = {}
    standalone_findings: List[Finding] = []

    for f in eligible_findings:
        if f.finding_group:
            grouped_findings.setdefault(f.finding_group, []).append(f)
        else:
            standalone_findings.append(f)

    # 3. Evaluate Standalone Findings
    for finding in standalone_findings:
        # Check if there is a claim linking this finding to hypothesis
        claim_id = None
        for c in view.claims:
            if c.finding_id == finding.id and c.hypothesis_id == hypothesis.id:
                claim_id = c.claim_id
                break

        if not claim_id:
            continue

        verdict = view.verdict_for(claim_id)
        if not verdict or verdict.result not in {VerdictResult.SUPPORT, VerdictResult.REFUTE}:
            continue

        lr_entry = kb.lr_for_finding_disease(
            disease_name_or_code=hypothesis.name,
            finding_code_or_name=finding.code.display or finding.code.code,
        )
        if not lr_entry:
            continue

        is_present = (finding.assertion == Assertion.PRESENT)
        raw_lr = lr_entry.lr_positive if is_present else lr_entry.lr_negative
        if raw_lr is None:
            continue

        # Clip expert opinion
        effective_lr = clip_if_expert_opinion(raw_lr, lr_entry.quality)

        # Direction agreement check (docs/07 B2)
        # SUPPORT must go with LR > 1.0; REFUTE must go with LR < 1.0
        direction_ok = False
        if verdict.result == VerdictResult.SUPPORT and effective_lr > 1.0:
            direction_ok = True
        elif verdict.result == VerdictResult.REFUTE and effective_lr < 1.0:
            direction_ok = True

        if not direction_ok:
            # Direction disagreement -> LR = 1.0, flag for review
            flagged_kb_entries.append(lr_entry.id)
            effective_lr = 1.0

        if math.isclose(effective_lr, 1.0):
            # LR = 1.0 leaves score unchanged (log(1.0) = 0)
            continue

        current_log_odds += math.log(effective_lr)
        lr_trail.append(
            LRTrailEntry(
                finding_or_group=finding.id,
                lr=effective_lr,
                kb_entry=lr_entry.id,
                verdict_id=verdict.verdict_id,
            )
        )

    # 4. Evaluate Grouped Findings (docs/07 B3: avoid double-counting correlated evidence)
    for group_name, f_list in grouped_findings.items():
        # Check if any finding in the group has a verified link to this hypothesis
        group_lr_candidates: List[tuple[float, str, str]] = []  # (lr, kb_entry_id, verdict_id)

        for finding in f_list:
            claim_id = None
            for c in view.claims:
                if c.finding_id == finding.id and c.hypothesis_id == hypothesis.id:
                    claim_id = c.claim_id
                    break

            if not claim_id:
                continue

            verdict = view.verdict_for(claim_id)
            if not verdict or verdict.result not in {VerdictResult.SUPPORT, VerdictResult.REFUTE}:
                continue

            lr_entry = kb.lr_for_finding_disease(
                disease_name_or_code=hypothesis.name,
                finding_code_or_name=finding.code.display or finding.code.code,
            )
            if not lr_entry:
                continue

            is_present = (finding.assertion == Assertion.PRESENT)
            raw_lr = lr_entry.lr_positive if is_present else lr_entry.lr_negative
            if raw_lr is None:
                continue

            eff_lr = clip_if_expert_opinion(raw_lr, lr_entry.quality)

            direction_ok = False
            if verdict.result == VerdictResult.SUPPORT and eff_lr > 1.0:
                direction_ok = True
            elif verdict.result == VerdictResult.REFUTE and eff_lr < 1.0:
                direction_ok = True

            if not direction_ok:
                flagged_kb_entries.append(lr_entry.id)
                eff_lr = 1.0

            if not math.isclose(eff_lr, 1.0):
                group_lr_candidates.append((eff_lr, lr_entry.id, verdict.verdict_id))

        if not group_lr_candidates:
            continue

        # Look for an explicit combined group LR in the KB for this disease
        combined_entry = None
        for entry in kb.lr_entries:
            if (
                entry.finding_group == group_name and
                entry.is_group_combined and
                (entry.disease.code.lower() == hypothesis.name.lower() or
                 entry.disease.display.lower() == hypothesis.name.lower())
            ):
                combined_entry = entry
                break

        if combined_entry:
            comb_lr = combined_entry.lr_positive or 1.0
            comb_lr = clip_if_expert_opinion(comb_lr, combined_entry.quality)
            current_log_odds += math.log(comb_lr)
            lr_trail.append(
                LRTrailEntry(
                    finding_or_group=group_name,
                    lr=comb_lr,
                    kb_entry=combined_entry.id,
                    verdict_id=group_lr_candidates[0][2],
                )
            )
        else:
            # No combined entry: use the single strongest LR in the group (max divergence from 1.0)
            strongest = max(group_lr_candidates, key=lambda item: abs(math.log(item[0])))
            current_log_odds += math.log(strongest[0])
            lr_trail.append(
                LRTrailEntry(
                    finding_or_group=group_name,
                    lr=strongest[0],
                    kb_entry=strongest[1],
                    verdict_id=strongest[2],
                )
            )

    # 5. Calculate Final Raw and Calibrated Posteriors
    p_raw = log_odds_to_prob(current_log_odds)
    # Prototype baseline calibration: identity mapping until tuning set calibration is fit
    p_calibrated = p_raw
    band = assign_band(p_calibrated)

    return ScoreResult(
        hypothesis_id=hypothesis.id,
        hypothesis_name=hypothesis.name,
        must_not_miss=hypothesis.must_not_miss,
        prior=prior,
        p_raw=p_raw,
        p_calibrated=p_calibrated,
        band=band,
        lr_trail=lr_trail,
        flagged_kb_entries=flagged_kb_entries,
    )


def score_all_hypotheses(
    view: CaseView,
    kb: KB,
) -> tuple[List[ScoreResult], List[Hypothesis]]:
    """Score all candidate hypotheses in the CaseView.

    Returns:
        (scored_results, unscored_hypotheses)
    """
    scored: List[ScoreResult] = []
    unscored: List[Hypothesis] = []

    for hyp in view.hypotheses:
        result = score_hypothesis(hyp, view, kb)
        if result is not None:
            scored.append(result)
        else:
            unscored.append(hyp)

    # Sort scored hypotheses descending by calibrated posterior probability
    scored.sort(key=lambda s: s.p_calibrated, reverse=True)
    return scored, unscored
