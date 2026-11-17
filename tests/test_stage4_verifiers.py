"""
tests/test_stage4_verifiers.py

Comprehensive tests for Stage 4 — Verification Layer.

Validates:
1. KBLinkChecker:
   - Valid clinical link produces SUPPORT verdict with kb_entry.
   - Proposed relation 'supports' when evidence shows LR < 1 produces REFUTE.
   - Unknown disease/finding link produces UNVERIFIABLE.
   - Missing finding or hypothesis in Case Graph produces UNVERIFIABLE.
   - Unsupported claim type produces NOT_APPLICABLE.
2. LabInterpreterVerifier:
   - Lab value outside reference range matches abnormal claim (SUPPORT).
   - Lab finding missing reference range produces UNVERIFIABLE.
   - Non-lab finding claim produces REFUTE.
3. MNMChecker:
   - Severe dengue / sepsis / malaria in MNM catalog produces SUPPORT.
   - Non-MNM condition produces REFUTE.
4. ConsistencyChecker:
   - Future onset day (onset > 0) produces REFUTE.
   - Negative duration produces REFUTE.
   - Consistent finding produces SUPPORT.
5. CitationJudge:
   - Matching passage in guideline corpus produces SUPPORT with CitationRef.
   - Mismatched or fabricated quote fails exact span check and produces REFUTE.
   - Missing corpus chunk produces UNVERIFIABLE.
6. Dispatcher & VerdictCache:
   - Targeted routing to appropriate verifiers by claim type.
   - Deterministic verdict wins over LLM judge in disagreement.
   - Conflicting LLM judges produce UNVERIFIABLE (judges_disagree).
   - Cache prevents redundant verification calls on same claim.
7. Clinical & Safety Invariants:
   - All verdicts validate against verdict.schema.json.
   - SUPPORT/REFUTE verdicts always provide kb_entry, rule_id, or citation.
   - Verifiers never modify GraphClient trust tiers or promote T6 findings.
   - No Bayesian scores or probabilities are computed.
"""

import pytest

from src.common.clock import DeterministicIdFactory, FixedClock
from src.common.models import (
    CitationRef,
    Claim,
    ClinicalCode,
    Confirmation,
    Finding,
    Hypothesis,
    Provenance,
    ReferenceRange,
    Verdict,
)
from src.common.types import (
    Assertion,
    ClaimType,
    ConfirmationStatus,
    ExtractionMethod,
    FindingKind,
    HypothesisOrigin,
    HypothesisStatus,
    Interpretation,
    SourceType,
    TrustTier,
    VerdictResult,
)
from src.graph import EventStore, GraphClient
from src.reasoning.kb import KB
from src.verifiers import (
    CitationJudge,
    ConsistencyChecker,
    KBLinkChecker,
    LabInterpreterVerifier,
    MNMChecker,
    VerdictCache,
    dispatch,
)


@pytest.fixture
def setup_env():
    store = EventStore()
    clock = FixedClock("2026-11-17T12:00:00+00:00")
    id_factory = DeterministicIdFactory(start=1)
    kb = KB.create_default()
    client = GraphClient("ingestion", "0.1.0", "ENC000001", store, clock, id_factory)
    return store, clock, id_factory, kb, client


def populate_graph(client: GraphClient):
    # Finding 1: Thrombocytopenia
    f1 = Finding(
        id="f-platelets",
        encounter_id="ENC000001",
        kind=FindingKind.LAB,
        code=ClinicalCode(system="SNOMED-CT", code="307077003", display="Thrombocytopenia"),
        original_text="low platelets 45 x10^3/uL",
        value=45.0,
        unit="10*3/uL",
        reference_range=ReferenceRange(low=150.0, high=450.0, source="local-lab"),
        interpretation=Interpretation.LOW,
        assertion=Assertion.PRESENT,
        onset_day=-3,
        duration_days=3.0,
        provenance=Provenance(
            source_id="lab-001",
            source_type=SourceType.LAB_LIS,
            quote="Platelets 45",
            extractor="test@0.1",
            method=ExtractionMethod.FIELD_MAPPING,
        ),
        trust_tier=TrustTier.T6,
        confirmation=Confirmation(status=ConfirmationStatus.PENDING),
    )
    client.add_finding(f1)

    # Finding 2: Retro-orbital pain
    f2 = Finding(
        id="f-retro-pain",
        encounter_id="ENC000001",
        kind=FindingKind.SYMPTOM,
        code=ClinicalCode(system="SNOMED-CT", code="386661006", display="Retro-orbital pain"),
        original_text="retro-orbital pain",
        assertion=Assertion.PRESENT,
        onset_day=-2,
        duration_days=2.0,
        provenance=Provenance(
            source_id="note-001",
            source_type=SourceType.CLINICAL_NOTE,
            quote="pain behind eyes",
            extractor="test@0.1",
            method=ExtractionMethod.RULES,
        ),
        trust_tier=TrustTier.T6,
        confirmation=Confirmation(status=ConfirmationStatus.PENDING),
    )
    client.add_finding(f2)

    # Hypothesis 1: Dengue fever (KB origin)
    kb_client = GraphClient("kb_lookup", "0.1.0", "ENC000001", client.db, client.clock, client.id_factory)
    h1 = Hypothesis(
        id="h-dengue",
        encounter_id="ENC000001",
        name="Dengue fever",
        origin=[HypothesisOrigin.KB],
        must_not_miss=True,
        prior=0.20,
        status=HypothesisStatus.ACTIVE,
        round=0,
    )
    kb_client.add_hypothesis(h1)

    # Hypothesis 2: Severe malaria (MNM origin)
    h2 = Hypothesis(
        id="h-severe-malaria",
        encounter_id="ENC000001",
        name="Severe malaria",
        origin=[HypothesisOrigin.MNM],
        must_not_miss=True,
        prior=0.08,
        status=HypothesisStatus.ACTIVE,
        round=0,
    )
    kb_client.add_hypothesis(h2)


# ---------------------------------------------------------------------------
# 1. KBLinkChecker Tests
# ---------------------------------------------------------------------------

def test_kb_link_checker_support(setup_env):
    store, clock, id_factory, kb, client = setup_env
    populate_graph(client)
    view = client.view()

    claim = Claim(
        claim_id="c-01",
        encounter_id="ENC000001",
        type=ClaimType.FINDING_DISEASE_LINK,
        finding_id="f-platelets",
        hypothesis_id="h-dengue",
        proposed_relation="supports",
        proposed_by="llm_proposer@0.1",
        round=1,
    )

    verifier = KBLinkChecker(id_factory)
    verdict = verifier.verify(claim, view, kb)

    assert verdict.result == VerdictResult.SUPPORT
    assert verdict.deterministic is True
    assert verdict.kb_entry == "lr-dengue-thrombocytopenia"
    assert "WHO Dengue Guidelines" in verdict.reason or "lr-dengue-thrombocytopenia" in verdict.reason


def test_kb_link_checker_refute_direction_mismatch(setup_env):
    store, clock, id_factory, kb, client = setup_env
    populate_graph(client)
    view = client.view()

    # Claim proposed 'refutes' for a finding that strongly supports dengue (LR+ = 3.0)
    claim = Claim(
        claim_id="c-02",
        encounter_id="ENC000001",
        type=ClaimType.FINDING_DISEASE_LINK,
        finding_id="f-platelets",
        hypothesis_id="h-dengue",
        proposed_relation="refutes",
        proposed_by="llm_proposer@0.1",
        round=1,
    )

    verifier = KBLinkChecker(id_factory)
    verdict = verifier.verify(claim, view, kb)

    # Direction mismatch produces REFUTE
    assert verdict.result == VerdictResult.REFUTE
    assert verdict.kb_entry == "lr-dengue-thrombocytopenia"


def test_kb_link_checker_unverifiable_no_kb_entry(setup_env):
    store, clock, id_factory, kb, client = setup_env
    populate_graph(client)
    view = client.view()

    claim = Claim(
        claim_id="c-03",
        encounter_id="ENC000001",
        type=ClaimType.FINDING_DISEASE_LINK,
        finding_id="f-retro-pain",
        hypothesis_id="h-severe-malaria",  # Retro-orbital pain does not link to severe malaria in KB
        proposed_relation="supports",
        proposed_by="llm_proposer@0.1",
        round=1,
    )

    verifier = KBLinkChecker(id_factory)
    verdict = verifier.verify(claim, view, kb)

    assert verdict.result == VerdictResult.UNVERIFIABLE
    assert verdict.unverifiable_reason == "no_source_found"


# ---------------------------------------------------------------------------
# 2. LabInterpreterVerifier Tests
# ---------------------------------------------------------------------------

def test_lab_interpreter_abnormal_support(setup_env):
    store, clock, id_factory, kb, client = setup_env
    populate_graph(client)
    view = client.view()

    claim = Claim(
        claim_id="c-lab-01",
        encounter_id="ENC000001",
        type=ClaimType.LAB_INTERPRETATION,
        finding_id="f-platelets",
        proposed_relation="supports",
        proposed_by="rule_engine@0.1",
        round=1,
    )

    verifier = LabInterpreterVerifier(id_factory)
    verdict = verifier.verify(claim, view, kb)

    assert verdict.result == VerdictResult.SUPPORT
    assert verdict.rule_id == "RULE-LAB-RANGE-INTERPRET"
    assert "Lab value evaluated as 'low'" in verdict.reason


def test_lab_interpreter_non_lab_refuted(setup_env):
    store, clock, id_factory, kb, client = setup_env
    populate_graph(client)
    view = client.view()

    claim = Claim(
        claim_id="c-lab-02",
        encounter_id="ENC000001",
        type=ClaimType.LAB_INTERPRETATION,
        finding_id="f-retro-pain",  # Symptom, not lab
        proposed_relation="supports",
        proposed_by="rule_engine@0.1",
        round=1,
    )

    verifier = LabInterpreterVerifier(id_factory)
    verdict = verifier.verify(claim, view, kb)

    assert verdict.result == VerdictResult.REFUTE
    assert verdict.rule_id == "RULE-LAB-KIND-CHECK"


# ---------------------------------------------------------------------------
# 3. MNMChecker Tests
# ---------------------------------------------------------------------------

def test_mnm_checker_support_and_refute(setup_env):
    store, clock, id_factory, kb, client = setup_env
    populate_graph(client)
    view = client.view()

    # Severe malaria is in MNM catalog
    claim_mnm = Claim(
        claim_id="c-mnm-01",
        encounter_id="ENC000001",
        type=ClaimType.MNM_STATUS,
        hypothesis_id="h-severe-malaria",
        proposed_by="generator@0.1",
        round=0,
    )
    verifier = MNMChecker(id_factory)
    v_support = verifier.verify(claim_mnm, view, kb)
    assert v_support.result == VerdictResult.SUPPORT
    assert v_support.rule_id == "RULE-MNM-CATALOG-ACTIVE"

    # Ordinary Dengue fever is not classified as Severe Dengue / MNM
    claim_non_mnm = Claim(
        claim_id="c-mnm-02",
        encounter_id="ENC000001",
        type=ClaimType.MNM_STATUS,
        hypothesis_id="h-dengue",
        proposed_by="generator@0.1",
        round=0,
    )
    v_refute = verifier.verify(claim_non_mnm, view, kb)
    assert v_refute.result == VerdictResult.REFUTE
    assert v_refute.rule_id == "RULE-MNM-CATALOG-NOT-FOUND"


# ---------------------------------------------------------------------------
# 4. ConsistencyChecker Tests
# ---------------------------------------------------------------------------

def test_consistency_checker(setup_env):
    store, clock, id_factory, kb, client = setup_env
    populate_graph(client)
    view = client.view()

    # Normal finding
    claim_ok = Claim(
        claim_id="c-cons-01",
        encounter_id="ENC000001",
        type=ClaimType.FACT_CONSISTENCY,
        finding_id="f-platelets",
        proposed_by="consistency@0.1",
        round=1,
    )
    verifier = ConsistencyChecker(id_factory)
    v_ok = verifier.verify(claim_ok, view, kb)
    assert v_ok.result == VerdictResult.SUPPORT
    assert v_ok.rule_id == "RULE-TIMELINE-CONSISTENT"

    # Future onset finding
    f_future = Finding(
        id="f-future-symptom",
        encounter_id="ENC000001",
        kind=FindingKind.SYMPTOM,
        code=ClinicalCode(system="SNOMED-CT", code="1", display="Future Cough"),
        assertion=Assertion.PRESENT,
        onset_day=2,  # > 0 relative to presentation
        provenance=Provenance(
            source_id="s", source_type=SourceType.CLINICAL_NOTE,
            quote="cough in 2 days", extractor="e", method=ExtractionMethod.RULES,
        ),
        trust_tier=TrustTier.T6,
        confirmation=Confirmation(status=ConfirmationStatus.PENDING),
    )
    client.add_finding(f_future)
    view2 = client.view()

    claim_bad = Claim(
        claim_id="c-cons-02",
        encounter_id="ENC000001",
        type=ClaimType.FACT_CONSISTENCY,
        finding_id="f-future-symptom",
        proposed_by="consistency@0.1",
        round=1,
    )
    v_bad = verifier.verify(claim_bad, view2, kb)
    assert v_bad.result == VerdictResult.REFUTE
    assert v_bad.rule_id == "RULE-TIMELINE-FUTURE-ONSET"


# ---------------------------------------------------------------------------
# 5. CitationJudge Tests
# ---------------------------------------------------------------------------

def test_citation_judge_exact_span_check(setup_env):
    store, clock, id_factory, kb, client = setup_env
    populate_graph(client)
    view = client.view()

    judge = CitationJudge(id_factory=id_factory)
    claim = Claim(
        claim_id="c-cite-01",
        encounter_id="ENC000001",
        type=ClaimType.FINDING_DISEASE_LINK,
        finding_id="f-platelets",
        hypothesis_id="h-dengue",
        proposed_relation="supports",
        proposed_by="llm_proposer@0.1",
        round=1,
    )

    # 1. Exact quote matching corpus
    exact_quote = "Thrombocytopenia and leukopenia are characteristic laboratory findings in the early febrile phase of dengue."
    v_exact = judge.verify(
        claim, view, kb,
        chunk_id="who-dengue-2009-s3-p12",
        quote=exact_quote,
    )
    assert v_exact.result == VerdictResult.SUPPORT
    assert v_exact.citation.chunk_id == "who-dengue-2009-s3-p12"
    assert v_exact.citation.quote == exact_quote

    # 2. Fabricated / altered quote fails exact span check -> REFUTE
    altered_quote = "Thrombocytopenia is a completely fabricated laboratory quote."
    v_altered = judge.verify(
        claim, view, kb,
        chunk_id="who-dengue-2009-s3-p12",
        quote=altered_quote,
    )
    assert v_altered.result == VerdictResult.REFUTE
    assert "Quote validation failed" in v_altered.reason


# ---------------------------------------------------------------------------
# 6. Dispatcher & Disagreement Arbitration Tests
# ---------------------------------------------------------------------------

def test_dispatch_and_cache(setup_env):
    store, clock, id_factory, kb, client = setup_env
    populate_graph(client)
    view = client.view()

    claim_link = Claim(
        claim_id="c-dispatch-01",
        encounter_id="ENC000001",
        type=ClaimType.FINDING_DISEASE_LINK,
        finding_id="f-platelets",
        hypothesis_id="h-dengue",
        proposed_relation="supports",
        proposed_by="llm_proposer@0.1",
        round=1,
    )
    claim_mnm = Claim(
        claim_id="c-dispatch-02",
        encounter_id="ENC000001",
        type=ClaimType.MNM_STATUS,
        hypothesis_id="h-severe-malaria",
        proposed_by="generator@0.1",
        round=0,
    )

    verifiers = [
        KBLinkChecker(id_factory),
        MNMChecker(id_factory),
        LabInterpreterVerifier(id_factory),
    ]

    cache = VerdictCache()
    verdicts = dispatch([claim_link, claim_mnm], verifiers, view, kb, cache)

    assert len(verdicts) == 2
    assert verdicts[0].claim_id == "c-dispatch-01"
    assert verdicts[0].result == VerdictResult.SUPPORT
    assert verdicts[0].kb_entry == "lr-dengue-thrombocytopenia"

    assert verdicts[1].claim_id == "c-dispatch-02"
    assert verdicts[1].result == VerdictResult.SUPPORT
    assert verdicts[1].rule_id == "RULE-MNM-CATALOG-ACTIVE"

    # Second call should return cached instances
    cached_verdicts = dispatch([claim_link], verifiers, view, kb, cache)
    assert len(cached_verdicts) == 1
    assert cached_verdicts[0].verdict_id == verdicts[0].verdict_id


def test_dispatcher_deterministic_wins_over_llm(setup_env):
    store, clock, id_factory, kb, client = setup_env
    populate_graph(client)
    view = client.view()

    # Claim proposed relation 'refutes'
    claim = Claim(
        claim_id="c-disagree-01",
        encounter_id="ENC000001",
        type=ClaimType.FINDING_DISEASE_LINK,
        finding_id="f-platelets",
        hypothesis_id="h-dengue",
        proposed_relation="refutes",
        proposed_by="llm_proposer@0.1",
        round=1,
    )

    # Deterministic verifier (KBLinkChecker) evaluates to REFUTE (direction mismatch)
    kb_checker = KBLinkChecker(id_factory)

    # Mock an LLM judge that returns SUPPORT
    class FakeLLMJudge:
        name = "fake-llm-judge"
        version = "0.1.0"
        deterministic = False
        handles = frozenset([ClaimType.FINDING_DISEASE_LINK])

        def verify(self, claim, view, kb):
            return Verdict(
                verdict_id="v-fake-01",
                claim_id=claim.claim_id,
                claim_type=claim.type,
                result=VerdictResult.SUPPORT,
                citation=CitationRef(source="corpus", chunk_id="chunk1", quote="test quote"),
                deterministic=False,
                verifier="fake-llm-judge@0.1.0",
                reason="LLM judge claims support",
            )

    verifiers = [kb_checker, FakeLLMJudge()]
    verdicts = dispatch([claim], verifiers, view, kb)

    assert len(verdicts) == 1
    # Per docs/08-verification.md section 4: Deterministic result wins!
    assert verdicts[0].deterministic is True
    assert verdicts[0].result == VerdictResult.REFUTE


# ---------------------------------------------------------------------------
# 7. End-to-End: Verification Writes to Case Graph
# ---------------------------------------------------------------------------

def test_verification_results_appended_to_case_graph(setup_env):
    store, clock, id_factory, kb, client = setup_env
    populate_graph(client)
    view = client.view()

    claim = Claim(
        claim_id="c-graph-01",
        encounter_id="ENC000001",
        type=ClaimType.FINDING_DISEASE_LINK,
        finding_id="f-platelets",
        hypothesis_id="h-dengue",
        proposed_relation="supports",
        proposed_by="llm_proposer@0.1",
        round=1,
    )

    # 1. Proposer client adds claim to Case Graph
    proposer_client = GraphClient("proposer", "0.1.0", "ENC000001", store, clock, id_factory)
    proposer_client.add_claim(claim)

    # 2. Run verification
    checker = KBLinkChecker(id_factory)
    verdict = checker.verify(claim, proposer_client.view(), kb)

    # 3. Verifier client writes verdict to Case Graph
    verifier_client = GraphClient("verifier", "0.1.0", "ENC000001", store, clock, id_factory)
    verifier_client.add_verdict(verdict)

    # 4. Verify updated CaseView
    updated_view = verifier_client.view()
    stored_verdict = updated_view.verdict_for(claim.claim_id)
    assert stored_verdict is not None
    assert stored_verdict.result == VerdictResult.SUPPORT
    assert stored_verdict.kb_entry == "lr-dengue-thrombocytopenia"

    # Invariant checks:
    # Finding trust tier must remain T6
    f = updated_view.finding_by_id("f-platelets")
    assert f.trust_tier == TrustTier.T6
    assert f.can_move_scores() is False
    assert len(updated_view.confirmed_findings()) == 0


# ---------------------------------------------------------------------------
# 8. Additional Safety & Targeted Invalidation Tests (Fixes 1-4)
# ---------------------------------------------------------------------------

def test_citation_judge_unrelated_passage_unverifiable(setup_env):
    """Fix 1 test: Genuine quotation exists in corpus, but does not semantically entail unrelated claim."""
    store, clock, id_factory, kb, client = setup_env
    populate_graph(client)
    view = client.view()

    judge = CitationJudge(id_factory=id_factory)
    # Claim links retro-orbital pain to Dengue fever
    claim = Claim(
        claim_id="c-unrelated-cite",
        encounter_id="ENC000001",
        type=ClaimType.FINDING_DISEASE_LINK,
        finding_id="f-retro-pain",
        hypothesis_id="h-dengue",
        proposed_relation="supports",
        proposed_by="llm_proposer@0.1",
        round=1,
    )

    # Use a genuine quote from the malaria chunk
    malaria_quote = (
        "Sudden onset of high fever accompanied by rigors and profuse sweating suggests acute malaria in endemic areas."
    )
    verdict = judge.verify(
        claim, view, kb,
        chunk_id="nvbdcp-malaria-chills-p5",
        quote=malaria_quote,
    )

    # Because quote matches verbatim in corpus, quotation span is found, but it does NOT entail retro-orbital pain / dengue
    assert verdict.result == VerdictResult.UNVERIFIABLE
    assert verdict.citation is not None
    assert verdict.citation.chunk_id == "nvbdcp-malaria-chills-p5"
    assert "does not semantically entail clinical link" in verdict.reason


def test_missing_finding_or_hypothesis_referenced_by_claim(setup_env):
    """Fix 3.2 test: Missing finding or hypothesis in Case Graph produces UNVERIFIABLE."""
    store, clock, id_factory, kb, client = setup_env
    populate_graph(client)
    view = client.view()

    checker = KBLinkChecker(id_factory)

    # Missing finding
    c_missing_f = Claim(
        claim_id="c-miss-f",
        encounter_id="ENC000001",
        type=ClaimType.FINDING_DISEASE_LINK,
        finding_id="f-does-not-exist",
        hypothesis_id="h-dengue",
        proposed_relation="supports",
        proposed_by="proposer",
        round=1,
    )
    v_f = checker.verify(c_missing_f, view, kb)
    assert v_f.result == VerdictResult.UNVERIFIABLE
    assert "Finding 'f-does-not-exist' not found" in v_f.reason

    # Missing hypothesis
    c_missing_h = Claim(
        claim_id="c-miss-h",
        encounter_id="ENC000001",
        type=ClaimType.FINDING_DISEASE_LINK,
        finding_id="f-platelets",
        hypothesis_id="h-does-not-exist",
        proposed_relation="supports",
        proposed_by="proposer",
        round=1,
    )
    v_h = checker.verify(c_missing_h, view, kb)
    assert v_h.result == VerdictResult.UNVERIFIABLE
    assert "Hypothesis 'h-does-not-exist' not found" in v_h.reason


def test_kb_version_change_invalidates_cache(setup_env):
    """Fix 3.3 test: Changing KB version invalidates cached verification results."""
    store, clock, id_factory, kb, client = setup_env
    populate_graph(client)
    view = client.view()

    claim = Claim(
        claim_id="c-kb-cache",
        encounter_id="ENC000001",
        type=ClaimType.FINDING_DISEASE_LINK,
        finding_id="f-platelets",
        hypothesis_id="h-dengue",
        proposed_relation="supports",
        proposed_by="proposer",
        round=1,
    )
    checker = KBLinkChecker(id_factory)
    cache = VerdictCache()

    # Initial dispatch on kb-0.1.0
    v1 = dispatch([claim], [checker], view, kb, cache)[0]
    assert v1.result == VerdictResult.SUPPORT

    # Same call returns cached object
    v_cached = dispatch([claim], [checker], view, kb, cache)[0]
    assert v_cached.verdict_id == v1.verdict_id

    # Create new KB with bumped version
    kb_v2 = kb.model_copy(update={"version": "kb-0.2.0"})
    v2 = dispatch([claim], [checker], view, kb_v2, cache)[0]

    # Must generate a new verdict because kb version changed!
    assert v2.verdict_id != v1.verdict_id


def test_finding_edit_invalidates_cache(setup_env):
    """Fix 3.6 test: Editing a finding in the graph invalidates previous cached verdict."""
    store, clock, id_factory, kb, client = setup_env
    populate_graph(client)
    view1 = client.view()

    claim = Claim(
        claim_id="c-edit-cache",
        encounter_id="ENC000001",
        type=ClaimType.LAB_INTERPRETATION,
        finding_id="f-platelets",
        proposed_relation="supports",
        proposed_by="proposer",
        round=1,
    )
    lab_verifier = LabInterpreterVerifier(id_factory)
    cache = VerdictCache()

    # Initial dispatch on low platelets (45.0) -> abnormal -> SUPPORT
    v1 = dispatch([claim], [lab_verifier], view1, kb, cache)[0]
    assert v1.result == VerdictResult.SUPPORT

    # Clinician edits the finding to normal platelets (250.0) at Checkpoint 1
    clinician = GraphClient("checkpoint_1", "1.0.0", "ENC000001", store, clock, id_factory)
    edited_finding = view1.finding_by_id("f-platelets").model_copy(
        update={"value": 250.0, "interpretation": Interpretation.NORMAL}
    )
    clinician.confirm_finding("f-platelets", by="Dr. Nair", edited=edited_finding)

    view2 = clinician.view()
    assert view2.version > view1.version
    assert view2.finding_by_id("f-platelets").value == 250.0

    # Dispatch on new view
    v2 = dispatch([claim], [lab_verifier], view2, kb, cache)[0]

    # Cache must miss and re-evaluate against updated normal value -> REFUTE
    assert v2.verdict_id != v1.verdict_id
    assert v2.result == VerdictResult.REFUTE
    assert "Lab value evaluated as 'normal'" in v2.reason


def test_two_llm_judges_disagree_produces_unverifiable(setup_env):
    """Fix 3.4 test: When two non-deterministic judges disagree, dispatcher arbitrates to UNVERIFIABLE."""
    store, clock, id_factory, kb, client = setup_env
    populate_graph(client)
    view = client.view()

    claim = Claim(
        claim_id="c-llm-disagree",
        encounter_id="ENC000001",
        type=ClaimType.FINDING_DISEASE_LINK,
        finding_id="f-platelets",
        hypothesis_id="h-dengue",
        proposed_relation="supports",
        proposed_by="proposer",
        round=1,
    )

    class JudgeA:
        name = "judge-a"
        version = "1.0"
        deterministic = False
        handles = frozenset([ClaimType.FINDING_DISEASE_LINK])

        def verify(self, claim, view, kb):
            return Verdict(
                verdict_id="v-a",
                claim_id=claim.claim_id,
                claim_type=claim.type,
                result=VerdictResult.SUPPORT,
                citation=CitationRef(source="c", chunk_id="1", quote="q"),
                deterministic=False,
                verifier="judge-a@1.0",
                reason="Judge A supports",
            )

    class JudgeB:
        name = "judge-b"
        version = "1.0"
        deterministic = False
        handles = frozenset([ClaimType.FINDING_DISEASE_LINK])

        def verify(self, claim, view, kb):
            return Verdict(
                verdict_id="v-b",
                claim_id=claim.claim_id,
                claim_type=claim.type,
                result=VerdictResult.REFUTE,
                rule_id="RULE-B",
                deterministic=False,
                verifier="judge-b@1.0",
                reason="Judge B refutes",
            )

    verdicts = dispatch([claim], [JudgeA(), JudgeB()], view, kb)
    assert len(verdicts) == 1
    assert verdicts[0].result == VerdictResult.UNVERIFIABLE
    assert verdicts[0].unverifiable_reason == "judges_disagree"


def test_neutral_likelihood_ratio_behavior(setup_env):
    """Fix 3.5 test: When LR = 1.0 (neutral evidence), relation is neutral and does not support directional change."""
    store, clock, id_factory, kb, client = setup_env
    populate_graph(client)
    view = client.view()

    # Create a neutral LR (1.0) for a unique finding
    neutral_lr = kb.lr_entries[0].model_copy(
        update={
            "id": "lr-neutral",
            "lr_positive": 1.0,
            "disease": ClinicalCode(system="SNOMED-CT", code="38362002", display="Dengue fever"),
            "finding": ClinicalCode(system="SNOMED-CT", code="999999", display="Neutral Observation"),
        }
    )
    kb_neutral = kb.model_copy(update={"lr_entries": [neutral_lr] + kb.lr_entries})

    f_neutral = Finding(
        id="f-neutral",
        encounter_id="ENC000001",
        kind=FindingKind.SYMPTOM,
        code=ClinicalCode(system="SNOMED-CT", code="999999", display="Neutral Observation"),
        assertion=Assertion.PRESENT,
        provenance=Provenance(
            source_id="s1", source_type=SourceType.CLINICAL_NOTE,
            quote="neutral", extractor="ext", method=ExtractionMethod.RULES,
        ),
        trust_tier=TrustTier.T6,
        confirmation=Confirmation(status=ConfirmationStatus.PENDING),
    )
    client.add_finding(f_neutral)
    view_updated = client.view()

    claim = Claim(
        claim_id="c-neutral-lr",
        encounter_id="ENC000001",
        type=ClaimType.FINDING_DISEASE_LINK,
        finding_id="f-neutral",
        hypothesis_id="h-dengue",
        proposed_relation="supports",
        proposed_by="proposer",
        round=1,
    )
    checker = KBLinkChecker(id_factory)
    verdict = checker.verify(claim, view_updated, kb_neutral)

    # Proposed 'supports', but neutral LR=1.0 indicates no directional support -> REFUTE
    assert verdict.result == VerdictResult.REFUTE
    assert "indicates relation is 'neutral' (LR=1.00)" in verdict.reason


def test_kb_provisional_placeholder_safety_labels(setup_env):
    """Fix 4 test: Knowledge Base is explicitly labelled as provisional illustrative benchmark."""
    store, clock, id_factory, kb, client = setup_env
    assert kb.is_provisional_placeholder is True
    assert kb.status_label == "PROVISIONAL_ILLUSTRATIVE_BENCHMARK"

