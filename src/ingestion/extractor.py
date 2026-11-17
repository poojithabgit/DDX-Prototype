"""
src/ingestion/extractor.py

Stage 2: Clinical Finding Extraction from the 15-encounter adult sample.

What this file does (beginner explanation):
  It reads four CSV tables from sample_data/ and converts each row into a
  structured Finding object. Think of it as a translator that takes raw
  spreadsheet rows and turns them into typed, validated, traceable medical facts.

Four sources:
  1. symptoms_normalized  → kind="symptom"  (one Finding per symptom row)
  2. vitals               → kind="vital"    (up to 6 Findings per encounter)
  3. lab_results          → kind="lab"      (one Finding per lab row)
  4. medical_history      → kind="history" or "exposure"
                            (only recognised clinical concepts; not_recorded skipped)

Safety rules enforced here:
  - reference_diagnoses and differential_candidates are NEVER read as findings.
  - All findings get trust_tier=T6 and confirmation.status="pending".
  - Lab interpretation is calculated ONLY when both reference limits parse as
    valid numbers AND the unit situation is handled safely.
  - critical_low / critical_high are NOT assigned (no approved critical threshold
    source available in this prototype).
  - Absent symptoms preserve duration_days=None, never zero.
  - Provisional SNOMED mappings are accepted but flagged in finding_group.
  - Facts with missing provenance raise ProvenanceMissingError.
"""

from __future__ import annotations

import csv
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

from src.common.errors import (
    InvalidValueError,
    ProvenanceMissingError,
    RejectedFindingError,
    UnsupportedUnitError,
)
from src.common.models import (
    ClinicalCode,
    Confirmation,
    Finding,
    Provenance,
    ReferenceRange,
)
from src.common.types import (
    Assertion,
    ConfirmationStatus,
    ExtractionMethod,
    FindingKind,
    Interpretation,
    SourceType,
    TrustTier,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXTRACTOR_ID = "prototype-extractor@0.1.0"

# Physiologically plausible limits for sanity checks (from docs/02-ingestion.md).
# These are outer bounds — values outside them are physically impossible.
PLAUSIBILITY_LIMITS: dict[str, tuple[float, float]] = {
    "temperature_c":        (25.0,  45.0),
    "pulse_bpm":            (10.0, 300.0),
    "systolic_bp_mmhg":     (40.0, 300.0),
    "diastolic_bp_mmhg":    (10.0, 200.0),
    "respiratory_rate_min": (2.0,   80.0),
    "spo2_percent":         (50.0, 100.0),
}

# Vitals: field → (LOINC code, LOINC display, UCUM unit)
VITAL_LOINC: dict[str, tuple[str, str, str]] = {
    "temperature_c":        ("8310-5",  "Body temperature",                     "Cel"),
    "pulse_bpm":            ("8867-4",  "Heart rate",                           "/min"),
    "systolic_bp_mmhg":     ("8480-6",  "Systolic blood pressure",              "mm[Hg]"),
    "diastolic_bp_mmhg":    ("8462-4",  "Diastolic blood pressure",             "mm[Hg]"),
    "respiratory_rate_min": ("9279-1",  "Respiratory rate",                     "/min"),
    "spo2_percent":         ("2708-6",  "Oxygen saturation in Arterial blood",  "%"),
}

# Medical history: known clinical concept codes → (kind, assertion, SNOMED, display)
# We only extract values we can safely map to a clinical concept.
# Social history values map to kind=exposure.
HISTORY_MAP: dict[str, tuple[FindingKind, Assertion, str, str]] = {
    # past_medical_history
    "asthma":        (FindingKind.HISTORY,  Assertion.HISTORICAL, "195967001", "Asthma (disorder)"),
    "diabetes":      (FindingKind.HISTORY,  Assertion.HISTORICAL, "73211009",  "Diabetes mellitus (disorder)"),
    "hypertension":  (FindingKind.HISTORY,  Assertion.HISTORICAL, "38341003",  "Hypertension (disorder)"),
    # social_history
    "smoker_reported": (FindingKind.EXPOSURE, Assertion.PRESENT, "77176002", "Smoker (finding)"),
    # allergies — penicillin allergy is a clinically relevant history finding
    "penicillin_reported": (FindingKind.HISTORY, Assertion.HISTORICAL, "372687004", "Penicillin allergy (finding)"),
}

# Values that should be silently skipped (no finding produced)
SKIP_VALUES = {
    "not_recorded", "none_reported", "non_smoker_reported",
    "seasonal_allergy",  # too non-specific for a clinical finding without more data
    "cardiovascular_disease_reported",  # family history — not a patient finding from this table
    "diabetes_reported",  # family_history column value
}

# Known safe unit equivalences: (reported_unit, ucum_unit) pairs where
# the two strings differ only in formatting but represent the same quantity.
# We do NOT perform any numeric conversion — the value is used as-is.
EQUIVALENT_UNITS: set[tuple[str, str]] = {
    ("10^3/uL", "10*3/uL"),   # WBC, platelets: caret vs asterisk notation
    ("10*3/uL", "10^3/uL"),
    ("mIU/L",   "m[IU]/L"),   # TSH
    ("m[IU]/L", "mIU/L"),
}


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class ExtractionResult:
    """Everything the extractor produces for one full encounter batch.

    findings  : validated Finding objects, ready for the Case Graph.
    rejected  : records that were quarantined with reasons.
    flagged   : records that were kept but need clinician attention.
    """
    findings: list[Finding] = field(default_factory=list)
    rejected: list[dict]    = field(default_factory=list)
    flagged:  list[dict]    = field(default_factory=list)

    def add_rejected(self, source: str, reason: str, row: Optional[dict] = None) -> None:
        entry = {"source": source, "reason": reason}
        if row:
            entry["row"] = {k: v for k, v in row.items()}
        self.rejected.append(entry)
        logger.warning("REJECTED [%s]: %s", source, reason)

    def add_flagged(self, source: str, reason: str, finding_id: str = "") -> None:
        self.flagged.append({"source": source, "finding_id": finding_id, "reason": reason})
        logger.info("FLAGGED [%s] %s: %s", source, finding_id, reason)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pending_confirmation() -> Confirmation:
    """All T6 findings start life pending clinician review at Checkpoint 1."""
    return Confirmation(status=ConfirmationStatus.PENDING, by=None, at=None)


def _safe_float(value: str, field_name: str) -> Optional[float]:
    """Try to parse a string as float; return None if empty or non-numeric."""
    if not value or value.strip() == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _units_are_compatible(reported: str, ucum: str) -> bool:
    """Return True if reported and ucum units are safely comparable.

    We consider them compatible if they are identical, or if the pair is
    listed in EQUIVALENT_UNITS (same physical quantity, different notation).
    We never silently convert different physical quantities.
    """
    if reported == ucum:
        return True
    if (reported, ucum) in EQUIVALENT_UNITS:
        return True
    return False


def _interpret_lab(value: float, ref_low: float, ref_high: float) -> Interpretation:
    """Return LOW, NORMAL, or HIGH based on value vs reference range.

    IMPORTANT: We never return critical_low or critical_high here.
    Critical thresholds require an explicitly approved clinical source
    (see Decision 3 in the Stage 2 approval). This prototype does not
    have such a source, so critical values are classified as HIGH or LOW.
    """
    if value < ref_low:
        return Interpretation.LOW
    if value > ref_high:
        return Interpretation.HIGH
    return Interpretation.NORMAL


def _load_provenance_index(sample_dir: str) -> dict[tuple[str, str], list[dict]]:
    """Build a lookup: (patient_id, concept) → list of provenance rows.

    This lets extractors look up the source quote for a given fact without
    scanning the full table on every row.
    """
    idx: dict[tuple[str, str], list[dict]] = {}
    prov_path = os.path.join(sample_dir, "provenance.csv")
    with open(prov_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (row["patient_id"], row["fact"])
            idx.setdefault(key, []).append(row)
    return idx


def _make_finding_id(encounter_id: str, category: str, sequence: int) -> str:
    """Generate a deterministic, human-readable finding ID.

    Format: f-<encounter_id>-<category>-<4-digit-sequence>
    Example: f-ENC000001-sym-0003
    """
    return f"f-{encounter_id}-{category}-{sequence:04d}"


# ---------------------------------------------------------------------------
# Source 1: Symptoms
# ---------------------------------------------------------------------------

def extract_symptoms(sample_dir: str, result: ExtractionResult,
                     prov_index: dict) -> None:
    """Convert every row in symptoms_normalized.csv into a Finding.

    Trust tier: T6 (synthetic/unconfirmed extraction).
    Absent symptoms: duration_days preserved as None, never zero.
    Provisional mappings: extracted but noted in finding_group.
    """
    path = os.path.join(sample_dir, "symptoms_normalized.csv")
    seq: dict[str, int] = {}  # per-encounter sequence counter

    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            enc_id  = row["encounter_id"]
            pid     = row["patient_id"]
            concept = row["concept"]
            seq[enc_id] = seq.get(enc_id, 0) + 1
            fid = _make_finding_id(enc_id, "sym", seq[enc_id])

            # -- Terminology code
            snomed_id = row["snomed_concept_id"].strip()
            display   = row["snomed_display_name"].strip()
            mapping   = row["mapping_status"].strip()

            if not snomed_id:
                result.add_rejected(
                    "symptoms_normalized", f"No SNOMED ID for concept '{concept}'", row
                )
                continue

            code = ClinicalCode(
                system="SNOMED-CT",
                code=snomed_id,
                display=display if display else concept,
            )

            # -- Assertion
            raw_assertion = row["assertion"].strip().lower()
            try:
                assertion = Assertion(raw_assertion)
            except ValueError:
                result.add_rejected(
                    "symptoms_normalized",
                    f"Unknown assertion '{raw_assertion}' for concept '{concept}'",
                    row,
                )
                continue

            # -- Duration: preserve None for absent; parse float for present
            dur_raw = row.get("duration_days", "").strip()
            if assertion == Assertion.ABSENT:
                duration_days = None   # never invent a duration for a negative
            else:
                duration_days = _safe_float(dur_raw, "duration_days")

            # -- Provenance: look up the matching provenance row
            prov_rows = prov_index.get((pid, concept), [])
            if not prov_rows:
                # Provenance missing — keep but flag (synthetic dataset limitation)
                result.add_flagged(
                    "symptoms_normalized",
                    f"No provenance row found for concept '{concept}' (pid={pid})",
                    fid,
                )
                quote      = concept  # use concept name as minimal quote
                source_id  = row["source_id"]
            else:
                prov_row  = prov_rows[0]
                quote     = prov_row.get("source_quote") or concept
                source_id = row["source_id"]

            provenance = Provenance(
                source_id=source_id,
                source_type=SourceType.CLINICAL_NOTE,
                fhir_resource=None,
                char_start=None,
                char_end=None,
                quote=quote,
                speaker=None,
                timestamp_in_source=None,
                extractor=EXTRACTOR_ID,
                method=ExtractionMethod.RULES,
            )

            # -- finding_group: flag provisional mappings
            finding_group = "provisional_mapping" if mapping == "provisional" else None
            if mapping == "provisional":
                result.add_flagged(
                    "symptoms_normalized",
                    f"Concept '{concept}' has provisional SNOMED mapping — "
                    "requires clinical review before use in scoring",
                    fid,
                )

            finding = Finding(
                id=fid,
                encounter_id=enc_id,
                kind=FindingKind.SYMPTOM,
                code=code,
                original_text=concept,
                value=None,
                unit=None,
                reference_range=None,
                interpretation=Interpretation.NOT_APPLICABLE,
                assertion=assertion,
                onset_day=None,
                duration_days=duration_days,
                trend="unknown",
                finding_group=finding_group,
                provenance=provenance,
                confidence=None,
                trust_tier=TrustTier.T6,
                confirmation=_make_pending_confirmation(),
            )
            result.findings.append(finding)


# ---------------------------------------------------------------------------
# Source 2: Vitals
# ---------------------------------------------------------------------------

def extract_vitals(sample_dir: str, result: ExtractionResult,
                   prov_index: dict) -> None:
    """Convert each row in vitals.csv into individual vital-sign Findings.

    Each encounter row produces up to 6 Findings (one per vital sign).
    Trust tier: T6 — provenance is 'synthetic_unvalidated'.
    Physiological plausibility is checked; impossible values are rejected.
    """
    path = os.path.join(sample_dir, "vitals.csv")
    seq: dict[str, int] = {}

    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            enc_id = row["encounter_id"]
            pid    = row["patient_id"]
            src_id = row["source_id"]

            # Look up the provenance row for vitals
            prov_rows = prov_index.get((pid, "vitals"), [])
            quote = prov_rows[0]["source_quote"] if prov_rows else src_id

            for vital_field, (loinc_code, loinc_display, ucum_unit) in VITAL_LOINC.items():
                raw_val = row.get(vital_field, "").strip()
                if not raw_val:
                    result.add_flagged(
                        "vitals", f"{vital_field} missing for {enc_id}", ""
                    )
                    continue

                val_float = _safe_float(raw_val, vital_field)
                if val_float is None:
                    result.add_rejected(
                        "vitals",
                        f"{vital_field} value '{raw_val}' is not numeric for {enc_id}",
                        row,
                    )
                    continue

                # Plausibility check
                lo, hi = PLAUSIBILITY_LIMITS[vital_field]
                if not (lo <= val_float <= hi):
                    result.add_rejected(
                        "vitals",
                        f"{vital_field}={val_float} outside physiological limits "
                        f"[{lo}, {hi}] for {enc_id}",
                        row,
                    )
                    continue

                seq[enc_id] = seq.get(enc_id, 0) + 1
                fid = _make_finding_id(enc_id, "vit", seq[enc_id])

                provenance = Provenance(
                    source_id=src_id,
                    source_type=SourceType.VITALS_FORM,
                    fhir_resource=None,
                    char_start=None,
                    char_end=None,
                    quote=quote,
                    speaker=None,
                    timestamp_in_source=None,
                    extractor=EXTRACTOR_ID,
                    method=ExtractionMethod.FIELD_MAPPING,
                )

                finding = Finding(
                    id=fid,
                    encounter_id=enc_id,
                    kind=FindingKind.VITAL,
                    code=ClinicalCode(
                        system="LOINC",
                        code=loinc_code,
                        display=loinc_display,
                    ),
                    original_text=raw_val,
                    value=val_float,
                    unit=ucum_unit,
                    reference_range=None,
                    interpretation=Interpretation.NOT_APPLICABLE,
                    assertion=Assertion.PRESENT,
                    onset_day=0,
                    duration_days=None,
                    trend="single_value",
                    finding_group=None,
                    provenance=provenance,
                    confidence=None,
                    trust_tier=TrustTier.T6,
                    confirmation=_make_pending_confirmation(),
                )
                result.findings.append(finding)


# ---------------------------------------------------------------------------
# Source 3: Lab results
# ---------------------------------------------------------------------------

def extract_labs(sample_dir: str, result: ExtractionResult,
                 prov_index: dict) -> None:
    """Convert each row in lab_results.csv into a lab Finding.

    Interpretation is calculated ONLY when:
      - value is a valid float
      - reference_low and reference_high both parse as valid floats
      - reported unit and UCUM unit are safely comparable
    Otherwise interpretation = not_applicable and the record is flagged.
    critical_low / critical_high are NEVER assigned here.
    """
    path = os.path.join(sample_dir, "lab_results.csv")
    seq: dict[str, int] = {}

    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            enc_id    = row["encounter_id"]
            pid       = row["patient_id"]
            test_name = row["test_name"]
            src_id    = row["source_id"]
            loinc_num = row["loinc_num"].strip()
            loinc_dn  = row["loinc_long_common_name"].strip()
            raw_val   = row["value"].strip()
            unit      = row["unit"].strip()
            ucum_unit = row["ucum_unit"].strip()
            ref_low_s = row["reference_low"].strip()
            ref_hi_s  = row["reference_high"].strip()

            seq[enc_id] = seq.get(enc_id, 0) + 1
            fid = _make_finding_id(enc_id, "lab", seq[enc_id])

            # -- Parse value
            val_float = _safe_float(raw_val, test_name)
            if val_float is None:
                result.add_rejected(
                    "lab_results",
                    f"Non-numeric value '{raw_val}' for test '{test_name}' [{enc_id}]",
                    row,
                )
                continue

            # -- Parse reference limits
            ref_low_f  = _safe_float(ref_low_s, "reference_low")
            ref_high_f = _safe_float(ref_hi_s,  "reference_high")

            # -- Unit compatibility
            units_ok = _units_are_compatible(unit, ucum_unit)

            # -- Decide interpretation and reference_range
            ref_range   = None
            interp      = Interpretation.NOT_APPLICABLE
            flag_reason = None

            if not units_ok:
                flag_reason = (
                    f"Unit '{unit}' and UCUM unit '{ucum_unit}' are not "
                    f"in the safe equivalence list for test '{test_name}' [{enc_id}]. "
                    "Interpretation set to not_applicable."
                )
            elif ref_low_f is None or ref_high_f is None:
                flag_reason = (
                    f"Reference range missing or non-numeric for test "
                    f"'{test_name}' [{enc_id}]. Interpretation not calculated."
                )
            else:
                # Both limits valid and units compatible — calculate interpretation
                interp = _interpret_lab(val_float, ref_low_f, ref_high_f)
                ref_range = ReferenceRange(
                    low=ref_low_f,
                    high=ref_high_f,
                    source="local-lab",
                )

            if flag_reason:
                result.add_flagged("lab_results", flag_reason, fid)

            # -- Provenance: use the lab source ID as the quote
            provenance = Provenance(
                source_id=src_id,
                source_type=SourceType.LAB_LIS,
                fhir_resource=None,
                char_start=None,
                char_end=None,
                quote=f"{test_name}={raw_val} {unit}",
                speaker=None,
                timestamp_in_source=None,
                extractor=EXTRACTOR_ID,
                method=ExtractionMethod.FIELD_MAPPING,
            )

            # Use LOINC code (always present and verified in this dataset)
            code = ClinicalCode(
                system="LOINC",
                code=loinc_num,
                display=loinc_dn if loinc_dn else test_name,
            )

            finding = Finding(
                id=fid,
                encounter_id=enc_id,
                kind=FindingKind.LAB,
                code=code,
                original_text=f"{test_name}={raw_val} {unit}",
                value=val_float,
                unit=ucum_unit if units_ok else unit,
                reference_range=ref_range,
                interpretation=interp,
                assertion=Assertion.PRESENT,
                onset_day=0,
                duration_days=None,
                trend="single_value",
                finding_group=None,
                provenance=provenance,
                confidence=None,
                trust_tier=TrustTier.T6,
                confirmation=_make_pending_confirmation(),
            )
            result.findings.append(finding)


# ---------------------------------------------------------------------------
# Source 4: Medical history
# ---------------------------------------------------------------------------

def extract_medical_history(sample_dir: str, result: ExtractionResult,
                             prov_index: dict) -> None:
    """Extract structured clinical findings from medical_history.csv.

    Rules:
      - Only values in HISTORY_MAP are extracted.
      - 'not_recorded', 'none_reported' and other generic strings are skipped.
      - 'smoker_reported' → kind=exposure, assertion=present (source says patient
        smokes; we do NOT assume current vs former without further source support).
      - 'penicillin_reported' → kind=history, assertion=historical.
      - Family history column is never extracted as a patient finding.
      - Original source value is always preserved in original_text.
    """
    path = os.path.join(sample_dir, "medical_history.csv")
    seq: dict[str, int] = {}

    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            enc_id = row["encounter_id"]
            pid    = row["patient_id"]
            src_id = row["history_source"]

            # We extract from three columns; family_history is explicitly excluded
            columns_to_extract = {
                "past_medical_history": row.get("past_medical_history", "").strip(),
                "allergies":            row.get("allergies", "").strip(),
                "social_history":       row.get("social_history", "").strip(),
            }

            for col_name, raw_value in columns_to_extract.items():
                if not raw_value or raw_value in SKIP_VALUES:
                    continue

                if raw_value not in HISTORY_MAP:
                    # Unknown value — skip silently (do not invent a finding)
                    logger.debug(
                        "Medical history value '%s' in col '%s' not in HISTORY_MAP — skipped",
                        raw_value, col_name,
                    )
                    continue

                kind, assertion, snomed_code, snomed_display = HISTORY_MAP[raw_value]

                seq[enc_id] = seq.get(enc_id, 0) + 1
                fid = _make_finding_id(enc_id, "hx", seq[enc_id])

                provenance = Provenance(
                    source_id=src_id,
                    source_type=SourceType.INTAKE_FORM,
                    fhir_resource=None,
                    char_start=None,
                    char_end=None,
                    quote=raw_value,       # original value is the source quote
                    speaker=None,
                    timestamp_in_source=None,
                    extractor=EXTRACTOR_ID,
                    method=ExtractionMethod.FIELD_MAPPING,
                )

                finding = Finding(
                    id=fid,
                    encounter_id=enc_id,
                    kind=kind,
                    code=ClinicalCode(
                        system="SNOMED-CT",
                        code=snomed_code,
                        display=snomed_display,
                    ),
                    original_text=raw_value,
                    value=None,
                    unit=None,
                    reference_range=None,
                    interpretation=Interpretation.NOT_APPLICABLE,
                    assertion=assertion,
                    onset_day=None,
                    duration_days=None,
                    trend="unknown",
                    finding_group=None,
                    provenance=provenance,
                    confidence=None,
                    trust_tier=TrustTier.T6,
                    confirmation=_make_pending_confirmation(),
                )
                result.findings.append(finding)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def extract_all_findings(sample_dir: str) -> ExtractionResult:
    """Run the full extraction pipeline for the 15-encounter adult sample.

    Steps:
      1. Load provenance index (lookup table for source quotes).
      2. Extract symptoms.
      3. Extract vitals.
      4. Extract lab results.
      5. Extract medical history.

    Returns an ExtractionResult with:
      - findings : list of validated Finding objects
      - rejected : records quarantined with reasons
      - flagged  : records kept but needing clinician attention

    Nothing is written to disk here. The Case Graph (Stage 3) handles persistence.
    """
    logger.info("Starting extraction from: %s", sample_dir)

    result = ExtractionResult()
    prov_index = _load_provenance_index(sample_dir)

    extract_symptoms(sample_dir, result, prov_index)
    logger.info("Symptoms extracted: %d findings", sum(
        1 for f in result.findings if f.kind == FindingKind.SYMPTOM
    ))

    extract_vitals(sample_dir, result, prov_index)
    logger.info("Vitals extracted: %d findings", sum(
        1 for f in result.findings if f.kind == FindingKind.VITAL
    ))

    extract_labs(sample_dir, result, prov_index)
    logger.info("Labs extracted: %d findings", sum(
        1 for f in result.findings if f.kind == FindingKind.LAB
    ))

    extract_medical_history(sample_dir, result, prov_index)
    logger.info("History/exposure extracted: %d findings", sum(
        1 for f in result.findings
        if f.kind in {FindingKind.HISTORY, FindingKind.EXPOSURE}
    ))

    logger.info(
        "Extraction complete — findings=%d, rejected=%d, flagged=%d",
        len(result.findings), len(result.rejected), len(result.flagged),
    )
    return result
