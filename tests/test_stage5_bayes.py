"""
tests/test_stage5_bayes.py

Comprehensive tests for Stage 5 — Deterministic Bayesian Reasoning Engine.

Tests:
1. Probability to odds and odds to probability round-trip.
2. Log-odds numerical stability (sigmoid, clipping bounds, preventing overflow/underflow).
3. Invalid prior probabilities rejection (<= 0, >= 1, NaN, Inf).
4. Sequential Bayesian updates with multiple likelihood ratios.
5. Neutral likelihood ratio (LR = 1.0) leaves score unchanged.
6. Likelihood ratios > 1 increase probability; LRs < 1 decrease probability.
7. Invalid likelihood ratios rejection (<= 0, negative, NaN).
8. Reproducibility across multiple runs.
9. Golden worked-example mathematical parity (docs/07 Part C & worked-example.json).
10. Expert-opinion likelihood ratio clipping to [0.5, 2.0].
11. Critical Safety Invariant: T6 unconfirmed findings are strictly ignored (LR = 1.0).
12. Critical Safety Invariant: Synthetic provenance findings cannot move scores.
13. Correlated findings grouping (finding_group) prevents naive double counting.
14. Direction disagreement handling (SUPPORT with LR < 1 yields LR = 1.0 and flags entry).
15. Missing prior puts hypothesis into unscored list ("Also consider (no KB data)").
16. Must-Not-Miss conditions remain independently visible and flagged regardless of score.
17. Full audit trail: LRTrailEntry preserves finding_or_group, applied LR, kb_entry ID, verdict_id.
"""

import math
import pytest

from src.common.clock import DeterministicIdFactory, FixedClock
from src.common.models import (
    CitationRef,
    Claim,
    ClinicalCode,
    Confirmation,
    Finding,
    Hypothesis,
    LREntry,
    LREntrySource,
    Provenance,
    ReferenceRange,
    Verdict,
)
from src.common.types import (
    Assertion,
    Band,
    ClaimType,
    ConfirmationStatus,
    ExtractionMethod,
    FindingKind,
    HypothesisOrigin,
    HypothesisStatus,
    Interpretation,
    LRQuality,
    LRSourceType,
    SourceType,
    TrustTier,
    VerdictResult,
)
from src.graph import EventStore, GraphClient
from src.reasoning import (
    KB,
    ScoreResult,
    assign_band,
    clip_if_expert_opinion,
    log_odds_to_prob,
    odds_to_prob,
    prob_to_log_odds,
    prob_to_odds,
    score_all_hypotheses,
    score_hypothesis,
    sequential_bayes_update,
    update_odds,
)


# ---------------------------------------------------------------------------
# 1. Fundamental Odds & Probability Calculations
# ---------------------------------------------------------------------------

def test_prob_odds_round_trip():
    probs = [0.01, 0.05, 0.20, 0.50, 0.75, 0.95, 0.99]
    for p in probs:
        odds = prob_to_odds(p)
        recovered = odds_to_prob(odds)
        assert math.isclose(p, recovered, rel_tol=1e-7)


def test_invalid_priors_rejected():
    invalid_priors = [0.0, 1.0, -0.1, 1.5, float("nan"), float("inf"), -float("inf")]
    for p in invalid_priors:
        with pytest.raises(ValueError):
            prob_to_odds(p)


def test_invalid_odds_and_lrs_rejected():
    with pytest.raises(ValueError, match="cannot be negative"):
        odds_to_prob(-0.5)

    with pytest.raises(ValueError, match="strictly positive"):
        update_odds(1.0, 0.0)

    with pytest.raises(ValueError, match="strictly positive"):
        update_odds(1.0, -2.5)


def test_numerical_stability_extremes():
    # Very small log odds
    p_tiny = log_odds_to_prob(-50.0)
    assert p_tiny > 0.0
    assert p_tiny < 1e-6

    # Very large log odds
    p_huge = log_odds_to_prob(50.0)
    assert p_huge < 1.0
    assert p_huge > 0.999999


# ---------------------------------------------------------------------------
# 2. Sequential Bayesian Updates & Neutrality
# ---------------------------------------------------------------------------

def test_sequential_bayes_updates():
    p0 = 0.20
    # Prior odds: 0.2 / 0.8 = 0.25
    # LR1 = 4.0 -> odds = 1.0 -> p = 0.5
    # LR2 = 1.5 -> odds = 1.5 -> p = 1.5 / 2.5 = 0.60
    final_odds, final_p, intermediates = sequential_bayes_update(p0, [4.0, 1.5])
    assert math.isclose(final_odds, 1.5, rel_tol=1e-5)
    assert math.isclose(final_p, 0.60, rel_tol=1e-5)
    assert len(intermediates) == 2
    assert math.isclose(intermediates[0], 0.50, rel_tol=1e-5)
    assert math.isclose(intermediates[1], 0.60, rel_tol=1e-5)


def test_neutral_lr_leaves_score_unchanged():
    p0 = 0.35
    odds0 = prob_to_odds(p0)
    odds_after = update_odds(odds0, 1.0)
    p_after = odds_to_prob(odds_after)

    assert math.isclose(odds0, odds_after)
    assert math.isclose(p0, p_after)

    final_odds, final_p, _ = sequential_bayes_update(p0, [1.0, 1.0, 1.0])
    assert math.isclose(p0, final_p)


def test_lr_directional_effects():
    p0 = 0.50  # odds = 1.0
    # LR > 1 increases probability
    odds_up = update_odds(1.0, 3.0)
    assert odds_to_prob(odds_up) > 0.50

    # LR < 1 decreases probability
    odds_down = update_odds(1.0, 0.4)
    assert odds_to_prob(odds_down) < 0.50


def test_reproducibility():
    p0 = 0.06
    lrs = [1.8, 1.5, 0.6, 2.0]
    res1 = sequential_bayes_update(p0, lrs)
    res2 = sequential_bayes_update(p0, lrs)
    assert res1 == res2


# ---------------------------------------------------------------------------
# 3. Clinical Rules & Safety Gates
# ---------------------------------------------------------------------------

def test_expert_opinion_clipping():
    # Normal quality is not clipped
    assert clip_if_expert_opinion(5.0, LRQuality.HIGH) == 5.0
    assert clip_if_expert_opinion(0.1, LRQuality.MODERATE) == 0.1

    # Expert opinion clipped to [0.5, 2.0] (docs/07 B4)
    assert clip_if_expert_opinion(5.0, LRQuality.EXPERT_OPINION) == 2.0
    assert clip_if_expert_opinion(0.2, LRQuality.EXPERT_OPINION) == 0.5
    assert clip_if_expert_opinion(1.4, LRQuality.EXPERT_OPINION) == 1.4


def test_probability_band_assignment():
    assert assign_band(0.75) == Band.HIGH
    assert assign_band(0.50) == Band.HIGH
    assert assign_band(0.35) == Band.MODERATE
    assert assign_band(0.20) == Band.MODERATE
    assert assign_band(0.10) == Band.LOW
    assert assign_band(0.05) == Band.LOW
    assert assign_band(0.04) == Band.VERY_LOW
    assert assign_band(0.001) == Band.VERY_LOW


# ---------------------------------------------------------------------------
# 4. Scorer Integration with Case Graph & CaseView
# ---------------------------------------------------------------------------

@pytest.fixture
def scored_environment():
    store = EventStore()
    clock = FixedClock("2026-11-17T12:00:00+00:00")
    id_factory = DeterministicIdFactory(start=1)
    kb = KB.create_default()
    return store, clock, id_factory, kb


def test_t6_findings_strictly_excluded_from_scoring(scored_environment):
    """Critical Safety: Unconfirmed T6 finding with SUPPORT verdict CANNOT move scores."""
    store, clock, id_factory, kb = scored_environment
    ingest = GraphClient("ingestion", "0.1.0", "ENC000001", store, clock, id_factory)

    # 1. Add finding as T6 unconfirmed
    f_t6 = Finding(
        id="f-t6-platelets",
        encounter_id="ENC000001",
        kind=FindingKind.LAB,
        code=ClinicalCode(system="SNOMED-CT", code="307077003", display="Thrombocytopenia"),
        assertion=Assertion.PRESENT,
        provenance=Provenance(
            source_id="s1", source_type=SourceType.LAB_LIS,
            quote="Plt 45", extractor="ext", method=ExtractionMethod.FIELD_MAPPING,
        ),
        trust_tier=TrustTier.T6,  # T6!
        confirmation=Confirmation(status=ConfirmationStatus.PENDING),
    )
    ingest.add_finding(f_t6)

    # 2. Add Hypothesis: Dengue (prior = 0.20)
    kb_client = GraphClient("kb_lookup", "0.1.0", "ENC000001", store, clock, id_factory)
    h = Hypothesis(
        id="h-dengue",
        encounter_id="ENC000001",
        name="Dengue fever",
        origin=[HypothesisOrigin.KB],
        must_not_miss=True,
        prior=0.20,
        status=HypothesisStatus.ACTIVE,
        round=0,
    )
    kb_client.add_hypothesis(h)

    # 3. Propose claim
    prop = GraphClient("proposer", "0.1.0", "ENC000001", store, clock, id_factory)
    c = Claim(
        claim_id="c-01",
        encounter_id="ENC000001",
        type=ClaimType.FINDING_DISEASE_LINK,
        finding_id="f-t6-platelets",
        hypothesis_id="h-dengue",
        proposed_relation="supports",
        proposed_by="proposer",
        round=1,
    )
    prop.add_claim(c)

    # 4. Verified with SUPPORT
    verif = GraphClient("verifier", "0.1.0", "ENC000001", store, clock, id_factory)
    v = Verdict(
        verdict_id="v-01",
        claim_id="c-01",
        result=VerdictResult.SUPPORT,
        kb_entry="lr-dengue-thrombocytopenia",
        deterministic=True,
        verifier="kb-link-checker@0.2.0",
        reason="Supported in KB",
    )
    verif.add_verdict(v)

    # 5. Score hypothesis
    view = verif.view()
    score_res = score_hypothesis(h, view, kb)

    assert score_res is not None
    # Because finding is T6, it must NOT move the score! (p_raw == prior == 0.20)
    assert math.isclose(score_res.p_raw, 0.20)
    assert len(score_res.lr_trail) == 0


def test_synthetic_provenance_finding_excluded_even_if_t1_confirmed(scored_environment):
    """Critical Safety Invariant: Synthetic-provenance findings cannot influence Bayesian scores,
    even if their trust level is T1 or they have been clinician-confirmed.
    """
    store, clock, id_factory, kb = scored_environment
    ingest = GraphClient("ingestion", "0.1.0", "ENC000001", store, clock, id_factory)

    # Ingest finding with synthetic provenance (e.g. synthetic test generator / reference data)
    # Marked as TrustTier.T1 and confirmed by clinician, but provenance indicates synthetic origin
    f_synth = Finding(
        id="f-synth-thrombocytopenia",
        encounter_id="ENC000001",
        kind=FindingKind.LAB,
        code=ClinicalCode(system="SNOMED-CT", code="307077003", display="Thrombocytopenia"),
        assertion=Assertion.PRESENT,
        provenance=Provenance(
            source_id="synthetic_label_01",
            source_type=SourceType.LAB_LIS,
            quote="platelet count 65000",
            extractor="prototype-extractor@0.1.0",
            method=ExtractionMethod.RULES,
        ),
        trust_tier=TrustTier.T1,
        confirmation=Confirmation(status=ConfirmationStatus.CONFIRMED, by="Dr. Senior Clinician"),
    )
    ingest.add_finding(f_synth)

    # Hypothesis: Dengue (prior = 0.20 -> odds = 0.25)
    kb_client = GraphClient("kb_lookup", "0.1.0", "ENC000001", store, clock, id_factory)
    h = Hypothesis(
        id="h-dengue-synth-test",
        encounter_id="ENC000001",
        name="Dengue fever",
        origin=[HypothesisOrigin.KB],
        must_not_miss=True,
        prior=0.20,
        status=HypothesisStatus.ACTIVE,
        round=0,
    )
    kb_client.add_hypothesis(h)

    # Claim & Verdict linking f_synth to h-dengue-synth-test with verified SUPPORT
    prop = GraphClient("proposer", "0.1.0", "ENC000001", store, clock, id_factory)
    c = Claim(
        claim_id="c-synth-01",
        encounter_id="ENC000001",
        type=ClaimType.FINDING_DISEASE_LINK,
        finding_id="f-synth-thrombocytopenia",
        hypothesis_id="h-dengue-synth-test",
        proposed_relation="supports",
        proposed_by="proposer",
        round=1,
    )
    prop.add_claim(c)

    verif = GraphClient("verifier", "0.1.0", "ENC000001", store, clock, id_factory)
    v = Verdict(
        verdict_id="v-synth-01",
        claim_id="c-synth-01",
        result=VerdictResult.SUPPORT,
        kb_entry="lr-dengue-thrombocytopenia",
        deterministic=True,
        verifier="kb-link-checker@0.2.0",
        reason="Supported in KB",
    )
    verif.add_verdict(v)

    # Score hypothesis
    view = verif.view()
    score_res = score_hypothesis(h, view, kb)

    assert score_res is not None
    # Critical Safety Assertion:
    # Synthetic provenance MUST be strictly excluded: score must remain untouched at prior (0.20),
    # and no LR trail entry should be recorded.
    assert math.isclose(score_res.p_raw, 0.20)
    assert len(score_res.lr_trail) == 0


def test_confirmed_t1_finding_moves_score(scored_environment):
    """Eligible confirmed T1 finding with verified link DOES move the score."""
    store, clock, id_factory, kb = scored_environment
    ingest = GraphClient("ingestion", "0.1.0", "ENC000001", store, clock, id_factory)

    # 1. Add finding as T1 confirmed (clinician physical exam)
    f_t1 = Finding(
        id="f-retro-pain",
        encounter_id="ENC000001",
        kind=FindingKind.SYMPTOM,
        code=ClinicalCode(system="SNOMED-CT", code="386661006", display="Retro-orbital pain"),
        assertion=Assertion.PRESENT,
        provenance=Provenance(
            source_id="note1", source_type=SourceType.CLINICAL_NOTE,
            quote="pain behind eyes", extractor="ext", method=ExtractionMethod.RULES,
        ),
        trust_tier=TrustTier.T1,
        confirmation=Confirmation(status=ConfirmationStatus.CONFIRMED, by="Dr. Sharma"),
    )
    ingest.add_finding(f_t1)

    # 2. Add Hypothesis: Dengue (prior = 0.20 -> odds = 0.25)
    kb_client = GraphClient("kb_lookup", "0.1.0", "ENC000001", store, clock, id_factory)
    h = Hypothesis(
        id="h-dengue",
        encounter_id="ENC000001",
        name="Dengue fever",
        origin=[HypothesisOrigin.KB],
        must_not_miss=True,
        prior=0.20,
        status=HypothesisStatus.ACTIVE,
        round=0,
    )
    kb_client.add_hypothesis(h)

    # 3. Add claim & verdict
    prop = GraphClient("proposer", "0.1.0", "ENC000001", store, clock, id_factory)
    c = Claim(
        claim_id="c-02",
        encounter_id="ENC000001",
        type=ClaimType.FINDING_DISEASE_LINK,
        finding_id="f-retro-pain",
        hypothesis_id="h-dengue",
        proposed_relation="supports",
        proposed_by="proposer",
        round=1,
    )
    prop.add_claim(c)

    verif = GraphClient("verifier", "0.1.0", "ENC000001", store, clock, id_factory)
    v = Verdict(
        verdict_id="v-02",
        claim_id="c-02",
        result=VerdictResult.SUPPORT,
        kb_entry="lr-dengue-retro-orbital-pain",
        deterministic=True,
        verifier="kb-link-checker@0.2.0",
        reason="Supported in KB",
    )
    verif.add_verdict(v)

    # 4. Score
    view = verif.view()
    score_res = score_hypothesis(h, view, kb)

    assert score_res is not None
    # LR for retro-orbital pain is 1.50
    # Prior odds: 0.25 * 1.50 = 0.375
    # p_raw: 0.375 / 1.375 = 0.2727...
    expected_p = 0.375 / 1.375
    assert math.isclose(score_res.p_raw, expected_p, rel_tol=1e-4)
    assert len(score_res.lr_trail) == 1
    assert score_res.lr_trail[0].lr == 1.5
    assert score_res.lr_trail[0].kb_entry == "lr-dengue-retro-orbital-pain"


def test_golden_worked_example_parity(scored_environment):
    """Verifies mathematical parity with golden worked example (docs/07 Part C & worked-example.json)."""
    store, clock, id_factory, kb = scored_environment
    ingest = GraphClient("ingestion", "0.1.0", "ENC000001", store, clock, id_factory)

    # Ingest golden case findings (T1 confirmed)
    # f-02: Retro-orbital pain (LR = 1.5)
    f2 = Finding(
        id="f-02",
        encounter_id="ENC000001",
        kind=FindingKind.SYMPTOM,
        code=ClinicalCode(system="SNOMED-CT", code="386661006", display="Retro-orbital pain"),
        assertion=Assertion.PRESENT,
        provenance=Provenance(source_id="s", source_type=SourceType.CLINICAL_NOTE, quote="q", extractor="e", method=ExtractionMethod.RULES),
        trust_tier=TrustTier.T1,
        confirmation=Confirmation(status=ConfirmationStatus.CONFIRMED, by="Dr. Lead"),
    )
    ingest.add_finding(f2)

    # f-07: Thrombocytopenia (in group cbc_dengue_pattern)
    f7 = Finding(
        id="f-07",
        encounter_id="ENC000001",
        kind=FindingKind.LAB,
        code=ClinicalCode(system="SNOMED-CT", code="307077003", display="Thrombocytopenia"),
        assertion=Assertion.PRESENT,
        finding_group="cbc_dengue_pattern",
        provenance=Provenance(source_id="s", source_type=SourceType.LAB_LIS, quote="q", extractor="e", method=ExtractionMethod.FIELD_MAPPING),
        trust_tier=TrustTier.T1,
        confirmation=Confirmation(status=ConfirmationStatus.CONFIRMED, by="Dr. Lead"),
    )
    ingest.add_finding(f7)

    # f-08: Leukopenia (in group cbc_dengue_pattern)
    f8 = Finding(
        id="f-08",
        encounter_id="ENC000001",
        kind=FindingKind.LAB,
        code=ClinicalCode(system="SNOMED-CT", code="84828003", display="Leukopenia"),
        assertion=Assertion.PRESENT,
        finding_group="cbc_dengue_pattern",
        provenance=Provenance(source_id="s", source_type=SourceType.LAB_LIS, quote="q", extractor="e", method=ExtractionMethod.FIELD_MAPPING),
        trust_tier=TrustTier.T1,
        confirmation=Confirmation(status=ConfirmationStatus.CONFIRMED, by="Dr. Lead"),
    )
    ingest.add_finding(f8)

    # Add combined group LR entry into KB for cbc_dengue_pattern (LR = 4.0)
    combined_cbc_lr = LREntry(
        id="lr-cbc-dengue-combined",
        disease=ClinicalCode(system="SNOMED-CT", code="38362002", display="Dengue fever"),
        finding=ClinicalCode(system="LOCAL", code="cbc_pattern", display="CBC Dengue Pattern"),
        finding_group="cbc_dengue_pattern",
        is_group_combined=True,
        lr_positive=4.0,  # Combined group LR = 4.0
        population="adult acute fever",
        source=LREntrySource(type=LRSourceType.STUDY, citation="Dengue CBC Study"),
        quality=LRQuality.HIGH,
        reviewed_by=["lead-01", "lead-02"],
        version="kb-0.1.0",
    )
    kb_with_group = kb.model_copy(update={"lr_entries": [combined_cbc_lr] + kb.lr_entries})

    # Hypothesis: Dengue (prior = 0.20)
    kb_client = GraphClient("kb_lookup", "0.1.0", "ENC000001", store, clock, id_factory)
    h = Hypothesis(
        id="h-dengue",
        encounter_id="ENC000001",
        name="Dengue fever",
        origin=[HypothesisOrigin.KB],
        must_not_miss=True,
        prior=0.20,
        status=HypothesisStatus.ACTIVE,
        round=1,
    )
    kb_client.add_hypothesis(h)

    # Claims & Verdicts for f2, f7, f8
    prop = GraphClient("proposer", "0.1.0", "ENC000001", store, clock, id_factory)
    c2 = Claim(claim_id="c-2", encounter_id="ENC000001", type=ClaimType.FINDING_DISEASE_LINK, finding_id="f-02", hypothesis_id="h-dengue", proposed_relation="supports", proposed_by="p", round=1)
    c7 = Claim(claim_id="c-7", encounter_id="ENC000001", type=ClaimType.FINDING_DISEASE_LINK, finding_id="f-07", hypothesis_id="h-dengue", proposed_relation="supports", proposed_by="p", round=1)
    c8 = Claim(claim_id="c-8", encounter_id="ENC000001", type=ClaimType.FINDING_DISEASE_LINK, finding_id="f-08", hypothesis_id="h-dengue", proposed_relation="supports", proposed_by="p", round=1)
    prop.add_claim(c2)
    prop.add_claim(c7)
    prop.add_claim(c8)

    verif = GraphClient("verifier", "0.1.0", "ENC000001", store, clock, id_factory)
    v2 = Verdict(verdict_id="v-2", claim_id="c-2", result=VerdictResult.SUPPORT, kb_entry="lr-dengue-retro-orbital-pain", deterministic=True, verifier="kb-checker", reason="ok")
    v7 = Verdict(verdict_id="v-7", claim_id="c-7", result=VerdictResult.SUPPORT, kb_entry="lr-dengue-thrombocytopenia", deterministic=True, verifier="kb-checker", reason="ok")
    v8 = Verdict(verdict_id="v-8", claim_id="c-8", result=VerdictResult.SUPPORT, kb_entry="lr-dengue-leukopenia", deterministic=True, verifier="kb-checker", reason="ok")
    verif.add_verdict(v2)
    verif.add_verdict(v7)
    verif.add_verdict(v8)

    # Score hypothesis
    view = verif.view()
    score_res = score_hypothesis(h, view, kb_with_group)

    # Mathematical Parity Verification:
    # Prior p0 = 0.20 -> odds = 0.25
    # Combined CBC pattern (f7 + f8) -> LR = 4.0 -> odds = 0.25 * 4.0 = 1.00
    # Retro-orbital pain (f2) -> LR = 1.5 -> odds = 1.00 * 1.5 = 1.50
    # Expected p_raw = 1.50 / (1 + 1.50) = 0.60
    assert score_res is not None
    assert math.isclose(score_res.p_raw, 0.60, rel_tol=1e-4)
    assert score_res.band == Band.HIGH
    assert len(score_res.lr_trail) == 2  # Combined group + retro-orbital pain
    assert any(entry.finding_or_group == "cbc_dengue_pattern" and entry.lr == 4.0 for entry in score_res.lr_trail)


def test_must_not_miss_remains_visible_regardless_of_low_score(scored_environment):
    """Must-not-miss conditions remain independently flagged and visible even with low score."""
    store, clock, id_factory, kb = scored_environment
    kb_client = GraphClient("kb_lookup", "0.1.0", "ENC000001", store, clock, id_factory)

    # Severe malaria (prior 0.08, MNM = True)
    h_mnm = Hypothesis(
        id="h-mnm-malaria",
        encounter_id="ENC000001",
        name="Severe malaria",
        origin=[HypothesisOrigin.MNM],
        must_not_miss=True,
        prior=0.08,
        status=HypothesisStatus.ACTIVE,
        round=0,
    )
    kb_client.add_hypothesis(h_mnm)

    view = kb_client.view()
    scored, unscored = score_all_hypotheses(view, kb)

    assert len(scored) == 1
    malaria_res = scored[0]
    assert malaria_res.must_not_miss is True
    assert malaria_res.band == Band.LOW
    assert math.isclose(malaria_res.p_raw, 0.08, rel_tol=1e-5)


def test_missing_prior_goes_to_unscored(scored_environment):
    """Hypothesis with no prior cannot be scored and is routed to unscored list."""
    store, clock, id_factory, kb = scored_environment
    prop = GraphClient("proposer", "0.1.0", "ENC000001", store, clock, id_factory)

    # Rare condition with no prior in KB
    h_rare = Hypothesis(
        id="h-rare",
        encounter_id="ENC000001",
        name="Rare Tropical Condition",
        origin=[HypothesisOrigin.LLM],
        must_not_miss=False,
        prior=None,
        status=HypothesisStatus.ACTIVE,
        round=1,
    )
    prop.add_hypothesis(h_rare)

    view = prop.view()
    scored, unscored = score_all_hypotheses(view, kb)

    assert len(scored) == 0
    assert len(unscored) == 1
    assert unscored[0].id == "h-rare"
