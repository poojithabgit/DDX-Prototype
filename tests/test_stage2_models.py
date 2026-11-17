"""
tests/test_stage2_models.py

Unit tests for Stage 2 shared Pydantic v2 models in src/common/.
Validates:
- Enums match schema values
- ClinicalCode validation
- Provenance validation
- Finding model validation against Pydantic and JSON Schema
- Finding trust tier methods (can_move_scores, is_confirmed)
- Hypothesis model validation
- Verdict model validation (SUPPORT/REFUTE requires evidence, UNVERIFIABLE does not)
- Claim model validation
- LREntry model validation (requires lr_positive, lr_negative, or sensitivity+specificity)
"""

import json
import os
import pytest
from pydantic import ValidationError

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
    Speaker,
    TrustTier,
    VerdictResult,
)
from src.common.models import (
    CitationRef,
    Claim,
    ClinicalCode,
    Confirmation,
    Finding,
    Hypothesis,
    LREntry,
    LREntrySource,
    LRTrailEntry,
    Provenance,
    ReferenceRange,
    ValidIllnessDays,
    Verdict,
)
from src.ingestion.validator import validate_finding


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

def test_enums_values():
    assert [t.value for t in TrustTier] == ["T1", "T2", "T3", "T4", "T5", "T6"]
    assert Assertion.PRESENT.value == "present"
    assert Assertion.ABSENT.value == "absent"
    assert Interpretation.NOT_APPLICABLE.value == "not_applicable"
    assert FindingKind.SYMPTOM.value == "symptom"
    assert SourceType.CLINICAL_NOTE.value == "clinical_note"
    assert ExtractionMethod.RULES.value == "rules"
    assert ConfirmationStatus.PENDING.value == "pending"


# ---------------------------------------------------------------------------
# ClinicalCode & Sub-models
# ---------------------------------------------------------------------------

def test_clinical_code_valid():
    code = ClinicalCode(system="SNOMED-CT", code="386661006", display="Fever")
    assert code.system == "SNOMED-CT"
    assert code.code == "386661006"


def test_clinical_code_invalid_system():
    with pytest.raises(ValidationError):
        ClinicalCode(system="INVALID-SYS", code="123", display="Test")


def test_provenance_valid():
    prov = Provenance(
        source_id="note_001",
        source_type=SourceType.CLINICAL_NOTE,
        quote="patient has high fever",
        extractor="extractor@1.0",
        method=ExtractionMethod.RULES,
    )
    assert prov.source_id == "note_001"
    assert prov.method == ExtractionMethod.RULES


def test_provenance_missing_required():
    with pytest.raises(ValidationError):
        # Missing extractor and method
        Provenance(
            source_id="note_001",
            source_type=SourceType.CLINICAL_NOTE,
        )


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------

def test_finding_valid_and_schema_validation():
    f = Finding(
        id="f-ENC000001-sym-0001",
        encounter_id="ENC000001",
        kind=FindingKind.SYMPTOM,
        code=ClinicalCode(system="SNOMED-CT", code="386661006", display="Fever"),
        original_text="fever",
        value=None,
        unit=None,
        reference_range=None,
        interpretation=Interpretation.NOT_APPLICABLE,
        assertion=Assertion.PRESENT,
        onset_day=-2,
        duration_days=3.0,
        trend="unknown",
        finding_group=None,
        provenance=Provenance(
            source_id="note_001",
            source_type=SourceType.CLINICAL_NOTE,
            quote="fever for 3 days",
            extractor="test@0.1",
            method=ExtractionMethod.RULES,
        ),
        confidence=0.95,
        trust_tier=TrustTier.T6,
        confirmation=Confirmation(status=ConfirmationStatus.PENDING),
    )
    assert f.id == "f-ENC000001-sym-0001"
    assert f.is_confirmed() is False
    assert f.can_move_scores() is False

    # Also validates against JSON schema
    validate_finding(f)


def test_finding_trust_tier_and_confirmation():
    # T6 confirmed still cannot move scores
    f_t6 = Finding(
        id="f-01",
        encounter_id="ENC01",
        kind=FindingKind.VITAL,
        code=ClinicalCode(system="LOINC", code="8310-5", display="Temp"),
        assertion=Assertion.PRESENT,
        provenance=Provenance(
            source_id="src_01",
            source_type=SourceType.VITALS_FORM,
            extractor="test@0.1",
            method=ExtractionMethod.FIELD_MAPPING,
        ),
        trust_tier=TrustTier.T6,
        confirmation=Confirmation(status=ConfirmationStatus.CONFIRMED),
    )
    assert f_t6.is_confirmed() is True
    assert f_t6.can_move_scores() is False

    # T1 confirmed CAN move scores
    f_t1 = f_t6.model_copy(update={"trust_tier": TrustTier.T1})
    assert f_t1.can_move_scores() is True


def test_finding_missing_required_fields():
    with pytest.raises(ValidationError):
        # Missing encounter_id, kind, code, etc.
        Finding(id="f-01")


# ---------------------------------------------------------------------------
# Hypothesis
# ---------------------------------------------------------------------------

def test_hypothesis_valid():
    h = Hypothesis(
        id="hyp-01",
        encounter_id="ENC000001",
        name="Dengue fever",
        origin=[HypothesisOrigin.KB, HypothesisOrigin.LLM],
        must_not_miss=True,
        prior=0.15,
        status=HypothesisStatus.ACTIVE,
        round=1,
    )
    assert h.name == "Dengue fever"
    assert h.must_not_miss is True
    assert h.round == 1


def test_hypothesis_missing_round():
    with pytest.raises(ValidationError):
        Hypothesis(
            id="hyp-01",
            encounter_id="ENC000001",
            name="Dengue",
            origin=[HypothesisOrigin.KB],
            must_not_miss=False,
            status=HypothesisStatus.ACTIVE,
        )


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------

def test_verdict_support_requires_evidence():
    # Without kb_entry, rule_id, or citation, SUPPORT must fail validation
    with pytest.raises(ValidationError):
        Verdict(
            verdict_id="v-01",
            claim_id="c-01",
            result=VerdictResult.SUPPORT,
            deterministic=True,
            verifier="rule_engine@1.0",
            reason="Supported without evidence",
        )

    # With rule_id, SUPPORT succeeds
    v = Verdict(
        verdict_id="v-01",
        claim_id="c-01",
        result=VerdictResult.SUPPORT,
        rule_id="RULE-001",
        deterministic=True,
        verifier="rule_engine@1.0",
        reason="Rule matches",
    )
    assert v.result == VerdictResult.SUPPORT


def test_verdict_unverifiable_does_not_require_evidence():
    v = Verdict(
        verdict_id="v-02",
        claim_id="c-02",
        result=VerdictResult.UNVERIFIABLE,
        deterministic=False,
        verifier="llm_verifier@1.0",
        reason="Corpus contains no evidence",
        unverifiable_reason="No match in KB",
    )
    assert v.result == VerdictResult.UNVERIFIABLE


# ---------------------------------------------------------------------------
# Claim
# ---------------------------------------------------------------------------

def test_claim_valid():
    c = Claim(
        claim_id="c-01",
        encounter_id="ENC000001",
        type=ClaimType.FINDING_DISEASE_LINK,
        finding_id="f-01",
        hypothesis_id="hyp-01",
        proposed_relation="supports",
        proposed_by="llm_agent@1.0",
        round=1,
    )
    assert c.claim_id == "c-01"
    assert c.proposed_relation == "supports"


def test_claim_invalid_relation():
    with pytest.raises(ValidationError):
        Claim(
            claim_id="c-01",
            encounter_id="ENC000001",
            type=ClaimType.FINDING_DISEASE_LINK,
            proposed_relation="invalid_relation",
            proposed_by="agent",
            round=1,
        )


# ---------------------------------------------------------------------------
# LREntry
# ---------------------------------------------------------------------------

def test_lr_entry_valid():
    lr = LREntry(
        id="lr-dengue-thrombocytopenia",
        disease=ClinicalCode(system="SNOMED-CT", code="38362002", display="Dengue fever"),
        finding=ClinicalCode(system="LOINC", code="777-3", display="Platelets"),
        lr_positive=4.5,
        population="Adult acute fever in India",
        source=LREntrySource(
            type=LRSourceType.SYSTEMATIC_REVIEW,
            citation="WHO Dengue Guidelines 2009",
        ),
        quality=LRQuality.HIGH,
        reviewed_by=["Dr. A", "Dr. B"],
        version="1.0",
    )
    assert lr.lr_positive == 4.5
    assert len(lr.reviewed_by) == 2


def test_lr_entry_must_have_lr_or_sn_sp():
    with pytest.raises(ValidationError):
        LREntry(
            id="lr-01",
            disease=ClinicalCode(system="SNOMED-CT", code="1", display="D"),
            finding=ClinicalCode(system="SNOMED-CT", code="2", display="F"),
            population="General",
            source=LREntrySource(type=LRSourceType.STUDY, citation="Study 2020"),
            quality=LRQuality.LOW,
            reviewed_by=["Dr. A", "Dr. B"],
            version="1.0",
        )
