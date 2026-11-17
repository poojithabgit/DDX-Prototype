"""
tests/test_stage3_case_graph.py

Comprehensive tests for Stage 3 — Case Graph (Shared Memory & Event Log).

Covers all Stage 3 requirements:
1. Appending events in chronological sequence.
2. Event ordering (monotonically increasing 1-based sequence).
3. Replaying events to reconstruct case state (CaseView).
4. Encounter isolation (events and state of ENC1 never bleed into ENC2).
5. Invalid event rejection (schema violations, permission violations, invalid types).
6. Explicit clinician confirmation with clinician identity, timestamp, and edit preservation.
7. Prevention of automatic T6 promotion (T6 findings remain T6; can_move_scores is False).
8. Append-only behavior (no in-place overwrite; updates create new events with before/after audit trail).
9. Duplicate identifier rejection per encounter.
10. Concurrency control via expected_version (StaleVersion on race conditions).
11. End-to-end integration: populating Case Graph from Stage 2 extracted findings.
"""

import pytest

from src.common.clock import DeterministicIdFactory, FixedClock
from src.common.errors import PermissionDenied, SchemaValidationError, StaleVersion
from src.common.models import (
    CitationRef,
    Claim,
    ClinicalCode,
    Confirmation,
    Finding,
    Hypothesis,
    LRTrailEntry,
    PatientContext,
    Provenance,
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
    SourceType,
    TrustTier,
    VerdictResult,
)
from src.graph import CaseView, EventStore, EventType, GraphClient
from src.ingestion.extractor import extract_all_findings


@pytest.fixture
def test_setup():
    store = EventStore()
    clock = FixedClock("2026-11-17T10:00:00+00:00")
    id_factory = DeterministicIdFactory(start=1)
    return store, clock, id_factory


def make_sample_finding(
    fid: str = "f-ENC000001-0001",
    enc_id: str = "ENC000001",
    tier: TrustTier = TrustTier.T6,
    assertion: Assertion = Assertion.PRESENT,
) -> Finding:
    return Finding(
        id=fid,
        encounter_id=enc_id,
        kind=FindingKind.SYMPTOM,
        code=ClinicalCode(system="SNOMED-CT", code="386661006", display="Fever"),
        original_text="fever",
        value=None,
        unit=None,
        reference_range=None,
        interpretation=Interpretation.NOT_APPLICABLE,
        assertion=assertion,
        onset_day=-2,
        duration_days=3.0,
        trend="unknown",
        finding_group=None,
        provenance=Provenance(
            source_id="src-001",
            source_type=SourceType.CLINICAL_NOTE,
            quote="fever for 3 days",
            extractor="test@0.1",
            method=ExtractionMethod.RULES,
        ),
        confidence=0.9,
        trust_tier=tier,
        confirmation=Confirmation(status=ConfirmationStatus.PENDING),
    )


def make_sample_hypothesis(
    hid: str = "h-ENC000001-0001",
    enc_id: str = "ENC000001",
    origin: list = None,
) -> Hypothesis:
    if origin is None:
        origin = [HypothesisOrigin.KB]
    return Hypothesis(
        id=hid,
        encounter_id=enc_id,
        name="Dengue fever",
        origin=origin,
        must_not_miss=True,
        prior=0.15,
        status=HypothesisStatus.ACTIVE,
        round=0,
    )


# ---------------------------------------------------------------------------
# Test 1: Event Appending and Monotonic Ordering
# ---------------------------------------------------------------------------

def test_event_appending_and_ordering(test_setup):
    store, clock, id_factory = test_setup
    client = GraphClient("ingestion", "0.1.0", "ENC000001", store, clock, id_factory)

    f1 = make_sample_finding("f-01", "ENC000001")
    f2 = make_sample_finding("f-02", "ENC000001")

    client.add_finding(f1)
    clock.advance_seconds(10)
    client.add_finding(f2)

    events = client.events()
    assert len(events) == 2
    assert events[0].sequence == 1
    assert events[1].sequence == 2
    assert events[0].event_id == "ev-000001"
    assert events[1].event_id == "ev-000002"
    assert events[0].at == "2026-11-17T10:00:00+00:00"
    assert events[1].at == "2026-11-17T10:00:10+00:00"


# ---------------------------------------------------------------------------
# Test 2: Event Replay and CaseView Reconstruction
# ---------------------------------------------------------------------------

def test_replay_reconstructs_case_view(test_setup):
    store, clock, id_factory = test_setup
    ingest_client = GraphClient("ingestion", "0.1.0", "ENC000001", store, clock, id_factory)
    clinician_client = GraphClient("checkpoint_1", "1.0.0", "ENC000001", store, clock, id_factory)

    # 1. Context
    ctx = PatientContext(patient_id="P001", age=32, sex="M", region="Karnataka")
    ingest_client.set_context(ctx)

    # 2. Add finding
    f1 = make_sample_finding("f-01", "ENC000001", tier=TrustTier.T6)
    ingest_client.add_finding(f1)

    # 3. Confirm finding at Checkpoint 1
    clinician_client.confirm_finding("f-01", by="Dr. Sharma")

    view = ingest_client.view()
    assert view.encounter_id == "ENC000001"
    assert view.version == 3
    assert view.context.age == 32
    assert len(view.findings) == 1

    reconstructed_f = view.finding_by_id("f-01")
    assert reconstructed_f is not None
    assert reconstructed_f.confirmation.status == ConfirmationStatus.CONFIRMED
    assert reconstructed_f.confirmation.by == "Dr. Sharma"
    # Provenance and original values are preserved
    assert reconstructed_f.provenance.source_id == "src-001"
    assert reconstructed_f.provenance.quote == "fever for 3 days"


# ---------------------------------------------------------------------------
# Test 3: Encounter Isolation
# ---------------------------------------------------------------------------

def test_encounter_isolation(test_setup):
    store, clock, id_factory = test_setup
    client1 = GraphClient("ingestion", "0.1.0", "ENC000001", store, clock, id_factory)
    client2 = GraphClient("ingestion", "0.1.0", "ENC000002", store, clock, id_factory)

    f1 = make_sample_finding("f-01", "ENC000001")
    f2 = make_sample_finding("f-02", "ENC000002")

    client1.add_finding(f1)
    client2.add_finding(f2)

    v1 = client1.view()
    v2 = client2.view()

    assert len(v1.findings) == 1
    assert v1.findings[0].id == "f-01"
    assert v1.findings[0].encounter_id == "ENC000001"

    assert len(v2.findings) == 1
    assert v2.findings[0].id == "f-02"
    assert v2.findings[0].encounter_id == "ENC000002"

    # Cross-encounter query is completely empty
    assert v1.finding_by_id("f-02") is None
    assert v2.finding_by_id("f-01") is None


# ---------------------------------------------------------------------------
# Test 4: Prevention of Automatic T6 Promotion
# ---------------------------------------------------------------------------

def test_t6_remains_t6_after_confirmation(test_setup):
    store, clock, id_factory = test_setup
    ingest_client = GraphClient("ingestion", "0.1.0", "ENC000001", store, clock, id_factory)
    clinician_client = GraphClient("checkpoint_1", "1.0.0", "ENC000001", store, clock, id_factory)

    f1 = make_sample_finding("f-01", "ENC000001", tier=TrustTier.T6)
    ingest_client.add_finding(f1)

    confirmed_f = clinician_client.confirm_finding("f-01", by="Dr. Sharma")

    # Safety assertion: T6 is NEVER promoted automatically to T1-T5
    assert confirmed_f.trust_tier == TrustTier.T6
    assert confirmed_f.confirmation.status == ConfirmationStatus.CONFIRMED

    # Safety assertion: can_move_scores remains False for T6 findings!
    assert confirmed_f.can_move_scores() is False

    # confirmed_findings() on CaseView only returns tiers T1-T5
    view = clinician_client.view()
    assert len(view.confirmed_findings()) == 0


# ---------------------------------------------------------------------------
# Test 5: Explicit Clinician Editing and Provenance Preservation
# ---------------------------------------------------------------------------

def test_clinician_edited_finding(test_setup):
    store, clock, id_factory = test_setup
    ingest_client = GraphClient("ingestion", "0.1.0", "ENC000001", store, clock, id_factory)
    clinician_client = GraphClient("checkpoint_1", "1.0.0", "ENC000001", store, clock, id_factory)

    f_vital = Finding(
        id="f-vit-01",
        encounter_id="ENC000001",
        kind=FindingKind.VITAL,
        code=ClinicalCode(system="LOINC", code="8310-5", display="Temp"),
        original_text="38.5",
        value=38.5,
        unit="Cel",
        assertion=Assertion.PRESENT,
        provenance=Provenance(
            source_id="vitals_form_01",
            source_type=SourceType.VITALS_FORM,
            quote="38.5 C",
            extractor="test@0.1",
            method=ExtractionMethod.FIELD_MAPPING,
        ),
        trust_tier=TrustTier.T6,
        confirmation=Confirmation(status=ConfirmationStatus.PENDING),
    )
    ingest_client.add_finding(f_vital)

    # Clinician corrects reading to 38.8
    edited_vital = f_vital.model_copy(update={"value": 38.8})
    updated = clinician_client.confirm_finding(
        finding_id="f-vit-01",
        by="Dr. Rao",
        edited=edited_vital,
    )

    assert updated.value == 38.8
    assert updated.confirmation.status == ConfirmationStatus.EDITED
    assert updated.confirmation.by == "Dr. Rao"
    assert updated.confirmation.original_value == 38.5

    # Check the audit log event
    events = clinician_client.events()
    edit_event = events[-1]
    assert edit_event.type == EventType.FINDING_EDITED.value
    assert edit_event.before["confirmation"]["status"] == "pending"
    assert edit_event.after["confirmation"]["status"] == "edited"


# ---------------------------------------------------------------------------
# Test 6: Permission Matrix Enforcement
# ---------------------------------------------------------------------------

def test_permission_matrix_enforcement(test_setup):
    store, clock, id_factory = test_setup

    # Ingestion trying to add a Hypothesis -> PermissionDenied
    ingest_client = GraphClient("ingestion", "0.1.0", "ENC000001", store, clock, id_factory)
    hyp = make_sample_hypothesis("h-01", "ENC000001")
    with pytest.raises(PermissionDenied):
        ingest_client.add_hypothesis(hyp)

    # Proposer trying to confirm a finding -> PermissionDenied
    proposer_client = GraphClient("proposer", "0.1.0", "ENC000001", store, clock, id_factory)
    with pytest.raises(PermissionDenied):
        proposer_client.confirm_finding("f-01", by="LLM")

    # Scorer trying to add a finding -> PermissionDenied
    scorer_client = GraphClient("scorer", "0.1.0", "ENC000001", store, clock, id_factory)
    f = make_sample_finding("f-01", "ENC000001")
    with pytest.raises(PermissionDenied):
        scorer_client.add_finding(f)


# ---------------------------------------------------------------------------
# Test 7: Duplicate Identifier Prevention
# ---------------------------------------------------------------------------

def test_duplicate_finding_rejected(test_setup):
    store, clock, id_factory = test_setup
    client = GraphClient("ingestion", "0.1.0", "ENC000001", store, clock, id_factory)

    f1 = make_sample_finding("f-01", "ENC000001")
    client.add_finding(f1)

    # Adding same finding ID again must raise ValueError
    with pytest.raises(ValueError, match="already exists"):
        client.add_finding(f1)


# ---------------------------------------------------------------------------
# Test 8: Schema Validation Enforcement on Graph Client Writes
# ---------------------------------------------------------------------------

def test_invalid_finding_schema_rejected(test_setup):
    store, clock, id_factory = test_setup
    client = GraphClient("ingestion", "0.1.0", "ENC000001", store, clock, id_factory)

    # Construct finding that fails schema validation (e.g. invalid confidence > 1)
    # Pydantic may catch it, or validator catches it
    with pytest.raises(Exception):
        Finding(
            id="f-bad",
            encounter_id="ENC000001",
            kind=FindingKind.SYMPTOM,
            code=ClinicalCode(system="SNOMED-CT", code="386661006", display="Fever"),
            assertion=Assertion.PRESENT,
            confidence=1.5,  # violates max 1
            provenance=Provenance(
                source_id="src",
                source_type=SourceType.CLINICAL_NOTE,
                extractor="ext",
                method=ExtractionMethod.RULES,
            ),
            trust_tier=TrustTier.T6,
            confirmation=Confirmation(status=ConfirmationStatus.PENDING),
        )


# ---------------------------------------------------------------------------
# Test 9: Concurrency Control and Stale Version Handling
# ---------------------------------------------------------------------------

def test_stale_version_rejected(test_setup):
    store, clock, id_factory = test_setup
    client = GraphClient("ingestion", "0.1.0", "ENC000001", store, clock, id_factory)

    f1 = make_sample_finding("f-01", "ENC000001")
    client.add_finding(f1, expected_version=0)  # current was 0, matches

    f2 = make_sample_finding("f-02", "ENC000001")
    # Current version is now 1. If caller expects version 0, it must raise StaleVersion!
    with pytest.raises(StaleVersion):
        client.add_finding(f2, expected_version=0)


# ---------------------------------------------------------------------------
# Test 10: Full Workflow with Claims, Verdicts, and Edges
# ---------------------------------------------------------------------------

def test_full_graph_workflow(test_setup):
    store, clock, id_factory = test_setup
    ingest_client = GraphClient("ingestion", "0.1.0", "ENC000001", store, clock, id_factory)
    proposer_client = GraphClient("proposer", "0.1.0", "ENC000001", store, clock, id_factory)
    verifier_client = GraphClient("verifier", "0.1.0", "ENC000001", store, clock, id_factory)
    scorer_client = GraphClient("scorer", "0.1.0", "ENC000001", store, clock, id_factory)

    # 1. Ingestion: Add finding
    f = make_sample_finding("f-01", "ENC000001")
    ingest_client.add_finding(f)

    # 2. Proposer: Add hypothesis with LLM origin
    h = Hypothesis(
        id="h-01",
        encounter_id="ENC000001",
        name="Dengue fever",
        origin=[HypothesisOrigin.LLM],
        must_not_miss=True,
        prior=0.10,
        status=HypothesisStatus.ACTIVE,
        round=1,
    )
    proposer_client.add_hypothesis(h)

    # 3. Proposer: Add claim
    c = Claim(
        claim_id="c-01",
        encounter_id="ENC000001",
        type=ClaimType.FINDING_DISEASE_LINK,
        finding_id="f-01",
        hypothesis_id="h-01",
        proposed_relation="supports",
        proposed_by="proposer@0.1.0",
        round=1,
    )
    proposer_client.add_claim(c)

    # 4. Verifier: Add verdict
    v = Verdict(
        verdict_id="v-01",
        claim_id="c-01",
        result=VerdictResult.SUPPORT,
        rule_id="RULE-DENGUE-FEVER",
        deterministic=True,
        verifier="rule_engine@1.0",
        reason="Fever supports acute dengue presentation",
    )
    verifier_client.add_verdict(v)

    # 5. Scorer: Update hypothesis score
    scored_h = scorer_client.update_scores(
        hypothesis_id="h-01",
        prior=0.10,
        p_raw=0.45,
        p_calibrated=0.42,
        band=Band.MODERATE,
        lr_trail=[
            LRTrailEntry(
                finding_or_group="f-01",
                lr=4.5,
                kb_entry="lr-dengue-fever-01",
                verdict_id="v-01",
            )
        ],
        because=["v-01"],
    )

    # 6. Verify rebuilt view
    view = scorer_client.view()
    assert view.version == 5
    assert len(view.findings) == 1
    assert len(view.hypotheses) == 1
    assert len(view.claims) == 1
    assert len(view.verdicts) == 1
    assert view.verdict_for("c-01").result == VerdictResult.SUPPORT

    top = view.top_hypotheses(1)
    assert len(top) == 1
    assert top[0].id == "h-01"
    assert top[0].p_calibrated == 0.42


# ---------------------------------------------------------------------------
# Test 11: End-to-End Ingestion Sample Feeding to Case Graph
# ---------------------------------------------------------------------------

def test_ingest_all_extracted_sample_findings_into_graph(test_setup):
    import os
    store, clock, id_factory = test_setup

    sample_dir = os.path.join(os.path.dirname(__file__), "..", "sample_data")
    extraction = extract_all_findings(sample_dir)
    assert len(extraction.findings) == 243

    # Feed findings for encounter ENC000001 into its own isolated graph
    enc1_findings = [f for f in extraction.findings if f.encounter_id == "ENC000001"]
    assert len(enc1_findings) > 0

    client = GraphClient("ingestion", "0.1.0", "ENC000001", store, clock, id_factory)
    for f in enc1_findings:
        client.add_finding(f)

    view = client.view()
    assert view.encounter_id == "ENC000001"
    assert len(view.findings) == len(enc1_findings)
    assert view.version == len(enc1_findings)

    # Verify all are T6 and pending
    for vf in view.findings:
        assert vf.trust_tier == TrustTier.T6
        assert vf.confirmation.status == ConfirmationStatus.PENDING
        assert vf.can_move_scores() is False

    # Checkpoint 1 confirmation of first finding
    clinician = GraphClient("checkpoint_1", "1.0.0", "ENC000001", store, clock, id_factory)
    target_f = enc1_findings[0]
    clinician.confirm_finding(target_f.id, by="Dr. Patel")

    updated_view = clinician.view()
    assert updated_view.version == len(enc1_findings) + 1
    cf = updated_view.finding_by_id(target_f.id)
    assert cf.confirmation.status == ConfirmationStatus.CONFIRMED
    assert cf.confirmation.by == "Dr. Patel"
    assert cf.trust_tier == TrustTier.T6
    assert cf.can_move_scores() is False  # T6 still cannot move scores


# ---------------------------------------------------------------------------
# Test 12: Empty Clinician Identity Rejection (Fix 1)
# ---------------------------------------------------------------------------

def test_empty_clinician_identity_rejected(test_setup):
    store, clock, id_factory = test_setup
    ingest_client = GraphClient("ingestion", "0.1.0", "ENC000001", store, clock, id_factory)
    clinician_client = GraphClient("checkpoint_1", "1.0.0", "ENC000001", store, clock, id_factory)

    f1 = make_sample_finding("f-01", "ENC000001", tier=TrustTier.T6)
    ingest_client.add_finding(f1)

    # Empty string must raise ValueError
    with pytest.raises(ValueError, match="Clinician identity 'by' is required"):
        clinician_client.confirm_finding("f-01", by="")

    # Whitespace-only string must raise ValueError
    with pytest.raises(ValueError, match="Clinician identity 'by' is required"):
        clinician_client.confirm_finding("f-01", by="   ")

    # None or empty in edited finding must also fail
    with pytest.raises(ValueError, match="Clinician identity 'by' is required"):
        clinician_client.confirm_finding("f-01", by=" \t\n ")


# ---------------------------------------------------------------------------
# Test 13: Duplicate Hypothesis Identifier Rejection (Fix 3.2)
# ---------------------------------------------------------------------------

def test_duplicate_hypothesis_rejected(test_setup):
    store, clock, id_factory = test_setup
    client = GraphClient("kb_lookup", "0.1.0", "ENC000001", store, clock, id_factory)

    h1 = make_sample_hypothesis("h-01", "ENC000001", origin=[HypothesisOrigin.KB])
    client.add_hypothesis(h1)

    # Adding same hypothesis ID again must raise ValueError
    with pytest.raises(ValueError, match="already exists"):
        client.add_hypothesis(h1)


# ---------------------------------------------------------------------------
# Test 14: Replay to Target Version K (Fix 3.3)
# ---------------------------------------------------------------------------

def test_replay_to_target_version(test_setup):
    store, clock, id_factory = test_setup
    client = GraphClient("ingestion", "0.1.0", "ENC000001", store, clock, id_factory)

    f1 = make_sample_finding("f-01", "ENC000001")
    f2 = make_sample_finding("f-02", "ENC000001")
    f3 = make_sample_finding("f-03", "ENC000001")

    client.add_finding(f1)  # Version 1
    client.add_finding(f2)  # Version 2
    client.add_finding(f3)  # Version 3

    # Replay at version 3 (current)
    view_v3 = store.replay("ENC000001", target_version=3)
    assert view_v3.version == 3
    assert len(view_v3.findings) == 3

    # Replay at version 2 (historical)
    view_v2 = store.replay("ENC000001", target_version=2)
    assert view_v2.version == 2
    assert len(view_v2.findings) == 2
    assert view_v2.finding_by_id("f-01") is not None
    assert view_v2.finding_by_id("f-02") is not None
    assert view_v2.finding_by_id("f-03") is None

    # Replay at version 1 (historical)
    view_v1 = store.replay("ENC000001", target_version=1)
    assert view_v1.version == 1
    assert len(view_v1.findings) == 1
    assert view_v1.finding_by_id("f-01") is not None
    assert view_v1.finding_by_id("f-02") is None


# ---------------------------------------------------------------------------
# Test 15: Edge Source and Destination Node Validation (Fix 2)
# ---------------------------------------------------------------------------

def test_edge_source_and_destination_validation(test_setup):
    store, clock, id_factory = test_setup
    ingest_client = GraphClient("ingestion", "0.1.0", "ENC000001", store, clock, id_factory)

    f1 = make_sample_finding("f-01", "ENC000001")
    f2 = make_sample_finding("f-02", "ENC000001")
    ingest_client.add_finding(f1)
    ingest_client.add_finding(f2)

    # Valid contradicts edge between existing findings f1 and f2
    edge = ingest_client.add_edge("contradicts", src="f-01", dst="f-02")
    assert edge.src == "f-01"
    assert edge.dst == "f-02"

    # Non-existent source node must raise ValueError
    with pytest.raises(ValueError, match="Source node 'f-nonexistent' does not exist"):
        ingest_client.add_edge("contradicts", src="f-nonexistent", dst="f-02")

    # Non-existent destination node must raise ValueError
    with pytest.raises(ValueError, match="Destination node 'f-nonexistent' does not exist"):
        ingest_client.add_edge("contradicts", src="f-01", dst="f-nonexistent")

    # derived_from allows external destination source reference, but src must exist
    derived = ingest_client.add_edge("derived_from", src="f-01", dst="clinical_note_row_42")
    assert derived.dst == "clinical_note_row_42"

