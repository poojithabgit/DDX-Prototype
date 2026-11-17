"""
tests/test_stage2_extractor.py

Comprehensive tests for clinical finding extraction (Stage 2).
Covers:
- Total finding count and distribution across categories (symptoms, vitals, labs, history/exposure)
- All findings assigned TrustTier.T6 and ConfirmationStatus.PENDING
- Absent symptoms preserve duration_days as None (never 0)
- Present symptoms have valid duration_days
- Lab findings interpretation (LOW, NORMAL, HIGH, NOT_APPLICABLE) and no critical values
- Unit compatibility checks for lab results
- Traceable provenance and source ids
- Medical history filtering and classification (asthma, smoker_reported, not_recorded skipped)
- No findings derived from reference_diagnoses or differential_candidates
- 100% JSON Schema and Pydantic validation pass rate for all extracted findings
"""

import os
import pytest

from src.common.types import (
    Assertion,
    ConfirmationStatus,
    FindingKind,
    Interpretation,
    TrustTier,
)
from src.ingestion.extractor import extract_all_findings
from src.ingestion.validator import validate_all, validate_finding


@pytest.fixture(scope="module")
def extraction_result():
    sample_dir = os.path.join(os.path.dirname(__file__), "..", "sample_data")
    return extract_all_findings(sample_dir)


def test_extraction_counts_and_categories(extraction_result):
    findings = extraction_result.findings
    assert len(findings) == 243

    symptoms = [f for f in findings if f.kind == FindingKind.SYMPTOM]
    vitals = [f for f in findings if f.kind == FindingKind.VITAL]
    labs = [f for f in findings if f.kind == FindingKind.LAB]
    history = [f for f in findings if f.kind == FindingKind.HISTORY]
    exposure = [f for f in findings if f.kind == FindingKind.EXPOSURE]

    assert len(symptoms) == 105
    assert len(vitals) == 90
    assert len(labs) == 32
    assert len(history) == 10
    assert len(exposure) == 6


def test_trust_tier_and_pending_status(extraction_result):
    for f in extraction_result.findings:
        assert f.trust_tier == TrustTier.T6, f"Finding {f.id} must be T6"
        assert f.confirmation.status == ConfirmationStatus.PENDING, f"Finding {f.id} must be pending"
        assert f.can_move_scores() is False, f"T6 finding {f.id} must not move scores"


def test_absent_symptoms_duration_none(extraction_result):
    symptoms = [f for f in extraction_result.findings if f.kind == FindingKind.SYMPTOM]
    absent = [s for s in symptoms if s.assertion == Assertion.ABSENT]
    present = [s for s in symptoms if s.assertion == Assertion.PRESENT]

    assert len(absent) == 38
    assert len(present) == 67

    for s in absent:
        assert s.duration_days is None, f"Absent symptom {s.id} should have duration_days=None, not 0"

    # Present symptoms should have duration >= 0 or None
    for s in present:
        if s.duration_days is not None:
            assert s.duration_days >= 0


def test_lab_interpretations_and_no_critical(extraction_result):
    labs = [f for f in extraction_result.findings if f.kind == FindingKind.LAB]
    assert len(labs) == 32

    interps = {f.interpretation for f in labs}
    assert interps.issubset({
        Interpretation.LOW,
        Interpretation.NORMAL,
        Interpretation.HIGH,
        Interpretation.NOT_APPLICABLE,
    })

    # Critical thresholds must NOT be assigned without an approved source
    assert Interpretation.CRITICAL_LOW not in interps
    assert Interpretation.CRITICAL_HIGH not in interps

    # Test high CRP examples
    high_crp = [
        f for f in labs
        if "CRP" in f.code.display or "C reactive protein" in f.code.display or "crp" in f.id.lower()
    ]
    # Check specific encounters known to have elevated CRP (ENC000011, ENC000017)
    enc11_crp = [f for f in labs if f.encounter_id == "ENC000011" and f.code.code == "1988-5"]
    assert len(enc11_crp) == 1
    assert enc11_crp[0].value == 33.6
    assert enc11_crp[0].interpretation == Interpretation.HIGH


def test_lab_unit_incompatibility_flagged(extraction_result):
    # WBC and platelets have 10^3/uL vs 10*3/uL in EQUIVALENT_UNITS, so they are compatible
    # But any incompatible labs or provisional mappings should be in flagged
    flagged = extraction_result.flagged
    assert len(flagged) == 9
    assert len(extraction_result.rejected) == 0


def test_medical_history_extraction(extraction_result):
    history_findings = [
        f for f in extraction_result.findings
        if f.kind in (FindingKind.HISTORY, FindingKind.EXPOSURE)
    ]
    assert len(history_findings) == 16

    # smoker_reported -> kind=exposure, assertion=present
    smokers = [f for f in history_findings if f.kind == FindingKind.EXPOSURE]
    assert len(smokers) == 6
    for s in smokers:
        assert s.original_text == "smoker_reported"
        assert s.assertion == Assertion.PRESENT
        assert s.code.code == "77176002"

    # asthma -> kind=history, assertion=historical
    asthma = [f for f in history_findings if f.original_text == "asthma"]
    for a in asthma:
        assert a.kind == FindingKind.HISTORY
        assert a.assertion == Assertion.HISTORICAL
        assert a.code.code == "195967001"


def test_provenance_completeness(extraction_result):
    for f in extraction_result.findings:
        assert f.provenance.source_id, f"Finding {f.id} missing source_id"
        assert f.provenance.extractor, f"Finding {f.id} missing extractor"
        assert f.provenance.method, f"Finding {f.id} missing method"
        assert f.provenance.quote, f"Finding {f.id} missing quote"


def test_no_reference_diagnoses_or_differential_candidates(extraction_result):
    for f in extraction_result.findings:
        src = f.provenance.source_type.value
        assert "reference_diagnoses" not in src
        assert "differential_candidates" not in src
        assert f.provenance.source_id != "reference_diagnoses"
        assert f.provenance.source_id != "differential_candidates"


def test_all_findings_pass_pydantic_and_schema_validation(extraction_result):
    valid, failures = validate_all(extraction_result.findings)
    assert len(failures) == 0, f"Schema validation failures: {failures}"
    assert len(valid) == 243
