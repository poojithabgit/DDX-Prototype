"""
src/common/types.py

Enumerations for every coded field used in the five JSON schemas.
Values are taken verbatim from the schema enum lists — do not change them
without also updating the schema files.

Plain-language guide for beginners:
  An "enum" is a fixed list of allowed text values. For example, TrustTier
  can only ever be T1, T2, T3, T4, T5, or T6 — nothing else is accepted.
  Using Python enums (instead of bare strings) means the program will
  immediately catch a typo like "t1" or "Tier1" rather than letting it
  silently produce wrong results.
"""

from enum import Enum


# ---------------------------------------------------------------------------
# Trust tiers — from finding.schema.json "trust_tier"
# ---------------------------------------------------------------------------
class TrustTier(str, Enum):
    """How much to trust a clinical fact, based on its source.

    T1 = Confirmed by the clinician (history or physical exam).
    T2 = Directly from the laboratory information system (LIS).
    T3 = Radiologist's written report.
    T4 = OCR-read value that the clinician has since confirmed.
    T5 = Imaging model output that passed the OOD (out-of-distribution) gate.
    T6 = Unconfirmed extraction — LLM, OCR, ASR, or synthetic template.
         T6 findings MUST NOT change any diagnostic probability.
    """
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"
    T4 = "T4"
    T5 = "T5"
    T6 = "T6"


# ---------------------------------------------------------------------------
# Assertion — from finding.schema.json "assertion"
# ---------------------------------------------------------------------------
class Assertion(str, Enum):
    """Whether the finding is present, absent, uncertain, etc.

    present   = Patient has this finding right now.
    absent    = Patient explicitly does NOT have this finding (pertinent negative).
    possible  = Uncertain — needs follow-up examination or test.
    historical= Patient had this in the past, not currently active.
    family    = A family member has/had this — exposure or genetic risk.
    unknown   = The source does not say either way.
    """
    PRESENT    = "present"
    ABSENT     = "absent"
    POSSIBLE   = "possible"
    HISTORICAL = "historical"
    FAMILY     = "family"
    UNKNOWN    = "unknown"


# ---------------------------------------------------------------------------
# Interpretation — from finding.schema.json "interpretation"
# ---------------------------------------------------------------------------
class Interpretation(str, Enum):
    """Interpretation of a measured value against a reference range.

    low/high/normal = within ordinary clinical ranges.
    critical_low/critical_high = outside the critical alert thresholds.
    abnormal = qualitatively abnormal (no numeric range applies).
    not_applicable = no reference range available, or not a numeric finding.

    IMPORTANT: critical_low and critical_high must come from an explicitly
    approved source. We never derive them from ordinary reference limits alone.
    """
    LOW            = "low"
    NORMAL         = "normal"
    HIGH           = "high"
    CRITICAL_LOW   = "critical_low"
    CRITICAL_HIGH  = "critical_high"
    ABNORMAL       = "abnormal"
    NOT_APPLICABLE = "not_applicable"


# ---------------------------------------------------------------------------
# FindingKind — from finding.schema.json "kind"
# ---------------------------------------------------------------------------
class FindingKind(str, Enum):
    """The category of clinical finding."""
    SYMPTOM           = "symptom"
    SIGN              = "sign"
    VITAL             = "vital"
    LAB               = "lab"
    EXPOSURE          = "exposure"
    HISTORY           = "history"
    MEDICATION_EFFECT = "medication_effect"
    IMAGING           = "imaging"


# ---------------------------------------------------------------------------
# SourceType — from finding.schema.json "provenance.source_type"
# ---------------------------------------------------------------------------
class SourceType(str, Enum):
    """The type of document or system the fact came from."""
    VITALS_FORM       = "vitals_form"
    EXAM_FORM         = "exam_form"
    INTAKE_FORM       = "intake_form"
    TRANSCRIPT        = "transcript"
    CLINICAL_NOTE     = "clinical_note"
    LAB_LIS           = "lab_lis"
    LAB_PDF           = "lab_pdf"
    LAB_PHOTO         = "lab_photo"
    EHR_FEED          = "ehr_feed"
    PHARMACY          = "pharmacy"
    IMAGING_MODEL     = "imaging_model"
    RADIOLOGY_REPORT  = "radiology_report"


# ---------------------------------------------------------------------------
# ExtractionMethod — from finding.schema.json "provenance.method"
# ---------------------------------------------------------------------------
class ExtractionMethod(str, Enum):
    """The technical method used to extract the fact."""
    FIELD_MAPPING = "field_mapping"
    RULES         = "rules"
    LLM           = "llm"
    OCR           = "ocr"
    ASR           = "asr"
    MODEL         = "model"


# ---------------------------------------------------------------------------
# Speaker — from finding.schema.json "provenance.speaker"
# ---------------------------------------------------------------------------
class Speaker(str, Enum):
    """Who said this, in a conversation source."""
    PATIENT   = "patient"
    DOCTOR    = "doctor"
    NURSE     = "nurse"
    ATTENDANT = "attendant"
    UNKNOWN   = "unknown"


# ---------------------------------------------------------------------------
# ConfirmationStatus — from finding.schema.json "confirmation.status"
# ---------------------------------------------------------------------------
class ConfirmationStatus(str, Enum):
    """Whether and how a clinician has reviewed this finding.

    not_required = Fact came from a trusted deterministic source (T1–T2).
    pending      = Needs clinician review (all T6 facts start here).
    confirmed    = Clinician accepted the extracted value as correct.
    edited       = Clinician changed the value; original_value is preserved.
    rejected     = Clinician determined this fact is incorrect or irrelevant.
    """
    NOT_REQUIRED = "not_required"
    PENDING      = "pending"
    CONFIRMED    = "confirmed"
    EDITED       = "edited"
    REJECTED     = "rejected"


# ---------------------------------------------------------------------------
# Band — from hypothesis.schema.json "band"
# ---------------------------------------------------------------------------
class Band(str, Enum):
    """Probability band for a hypothesis after scoring."""
    HIGH      = "HIGH"
    MODERATE  = "MODERATE"
    LOW       = "LOW"
    VERY_LOW  = "VERY_LOW"
    UNSCORED  = "UNSCORED"


# ---------------------------------------------------------------------------
# HypothesisOrigin — from hypothesis.schema.json "origin" items
# ---------------------------------------------------------------------------
class HypothesisOrigin(str, Enum):
    """Where the candidate diagnosis came from."""
    KB           = "KB"
    MNM          = "MNM"
    LLM          = "LLM"
    DRUG_CHECKER = "DRUG_CHECKER"
    CLINICIAN    = "CLINICIAN"


# ---------------------------------------------------------------------------
# HypothesisStatus — from hypothesis.schema.json "status"
# ---------------------------------------------------------------------------
class HypothesisStatus(str, Enum):
    """Current state of a candidate diagnosis."""
    ACTIVE                = "active"
    RULED_OUT             = "ruled_out"
    CONFIRMED_BY_CLINICIAN = "confirmed_by_clinician"
    REJECTED_BY_CLINICIAN  = "rejected_by_clinician"


# ---------------------------------------------------------------------------
# VerdictResult — from verdict.schema.json "result"
# ---------------------------------------------------------------------------
class VerdictResult(str, Enum):
    """The outcome of one verifier checking one claim."""
    SUPPORT        = "SUPPORT"
    REFUTE         = "REFUTE"
    UNVERIFIABLE   = "UNVERIFIABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


# ---------------------------------------------------------------------------
# ClaimType — from claim.schema.json "type"
# ---------------------------------------------------------------------------
class ClaimType(str, Enum):
    """The category of claim being made and checked."""
    FINDING_DISEASE_LINK = "FINDING_DISEASE_LINK"
    LAB_INTERPRETATION   = "LAB_INTERPRETATION"
    DRUG_CAUSE           = "DRUG_CAUSE"
    TEST_SAFETY          = "TEST_SAFETY"
    FACT_CONSISTENCY     = "FACT_CONSISTENCY"
    IMAGING_FINDING      = "IMAGING_FINDING"
    MNM_STATUS           = "MNM_STATUS"


# ---------------------------------------------------------------------------
# LRQuality — from likelihood-ratio.schema.json "quality"
# ---------------------------------------------------------------------------
class LRQuality(str, Enum):
    """Quality of the evidence behind a likelihood ratio."""
    HIGH           = "high"
    MODERATE       = "moderate"
    LOW            = "low"
    EXPERT_OPINION = "expert-opinion"


# ---------------------------------------------------------------------------
# LRSourceType — from likelihood-ratio.schema.json "source.type"
# ---------------------------------------------------------------------------
class LRSourceType(str, Enum):
    """Type of publication or data behind a likelihood ratio."""
    SYSTEMATIC_REVIEW  = "systematic_review"
    STUDY              = "study"
    RATIONAL_CLINICAL  = "rational_clinical_exam"
    LOCAL_DATA         = "local_data"
    MODEL_VALIDATION   = "model_validation"
    EXPERT_OPINION     = "expert_opinion"
