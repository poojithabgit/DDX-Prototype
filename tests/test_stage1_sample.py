"""
Test suite to verify the integrity, referential validity, and safety properties
of the extracted 15-encounter adult sample in sample_data/.
"""

import os
import csv
import json
import pytest

SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "..", "sample_data")

TABLES = [
    "patients",
    "encounters",
    "symptoms_normalized",
    "vitals",
    "medical_history",
    "lab_results",
    "medications",
    "differential_candidates",
    "provenance",
    "timeline",
    "reference_diagnoses",
]

def load_csv(table_name: str) -> list[dict]:
    path = os.path.join(SAMPLE_DIR, f"{table_name}.csv")
    assert os.path.exists(path), f"CSV file not found: {path}"
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def load_jsonl(table_name: str) -> list[dict]:
    path = os.path.join(SAMPLE_DIR, f"{table_name}.jsonl")
    assert os.path.exists(path), f"JSONL file not found: {path}"
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

@pytest.mark.parametrize("table_name", TABLES)
def test_csv_jsonl_parity(table_name: str):
    """CSV and JSONL must have identical row count and matching keys."""
    csv_rows = load_csv(table_name)
    jsonl_rows = load_jsonl(table_name)

    assert len(csv_rows) == len(jsonl_rows), (
        f"Row count mismatch in {table_name}: CSV has {len(csv_rows)}, JSONL has {len(jsonl_rows)}"
    )

    if csv_rows:
        csv_keys = set(csv_rows[0].keys())
        jsonl_keys = set(jsonl_rows[0].keys())
        assert csv_keys == jsonl_keys, f"Field key mismatch in {table_name}"

def test_cohort_size_and_adult_filtering():
    """Verify sample contains exactly 15 adult patients with age >= 18."""
    patients = load_csv("patients")
    encounters = load_csv("encounters")

    assert len(patients) == 15, f"Expected 15 patients, found {len(patients)}"
    assert len(encounters) == 15, f"Expected 15 encounters, found {len(encounters)}"

    for pt in patients:
        age = int(pt["age_years"])
        assert age >= 18, f"Patient {pt['patient_id']} is not an adult (age={age})"

def test_referential_integrity():
    """Verify 100% valid foreign keys across all child tables."""
    patients = load_csv("patients")
    encounters = load_csv("encounters")

    valid_patients = {p["patient_id"] for p in patients}
    valid_encounters = {e["encounter_id"] for e in encounters}

    # 1. encounters -> patients
    for enc in encounters:
        assert enc["patient_id"] in valid_patients, (
            f"Orphaned patient_id in encounters: {enc['patient_id']}"
        )

    # 2. Child tables with patient_id and/or encounter_id
    for table_name in TABLES:
        if table_name in ("patients", "encounters"):
            continue

        rows = load_csv(table_name)
        for row in rows:
            if "patient_id" in row:
                assert row["patient_id"] in valid_patients, (
                    f"Orphaned patient_id {row['patient_id']} in {table_name}"
                )
            if "encounter_id" in row:
                assert row["encounter_id"] in valid_encounters, (
                    f"Orphaned encounter_id {row['encounter_id']} in {table_name}"
                )

def test_missing_clinical_duration_preservation():
    """Verify missing symptom durations were not replaced with zero."""
    symptoms = load_csv("symptoms_normalized")
    absent_symptoms = [s for s in symptoms if s.get("assertion") == "absent"]
    assert len(absent_symptoms) > 0, "No absent symptoms found in sample"

    for s in absent_symptoms:
        dur = s.get("duration_days", "")
        # Should be empty string or null, never 0.0 or 0
        assert dur in ("", None, "null"), (
            f"Absent symptom duration erroneously replaced with zero: {s}"
        )

def test_differential_score_safety():
    """Verify demo differential scores are demarcated as non-Bayesian."""
    candidates = load_csv("differential_candidates")
    assert len(candidates) > 0, "No differential candidates in sample"

    for c in candidates:
        assert c["is_bayesian_probability"] in ("False", "false", False), (
            f"Candidate score must have is_bayesian_probability=False: {c}"
        )
        assert c["score_interpretation"] == "synthetic_demo_score_not_calibrated_probability"

def test_reference_diagnosis_policy():
    """Verify reference diagnoses are clearly labeled as evaluation truth only."""
    ref_diag = load_csv("reference_diagnoses")
    assert len(ref_diag) == 15, "Expected 15 reference diagnoses"

    for rd in ref_diag:
        assert rd["label_role"] == "synthetic_reference_label_not_clinical_diagnosis"
        assert rd["validation_status"] == "not_clinically_validated"

def test_terminology_mappings_present():
    """Verify mapping files exist in sample_data/mappings/ with expected concept counts."""
    mapping_dir = os.path.join(SAMPLE_DIR, "mappings")
    assert os.path.exists(mapping_dir), "Mappings folder missing in sample_data"

    sym_path = os.path.join(mapping_dir, "symptoms_snomed_mapping.csv")
    lab_path = os.path.join(mapping_dir, "labs_loinc_mapping.csv")
    cond_path = os.path.join(mapping_dir, "conditions_icd10_snomed_mapping.csv")

    assert os.path.exists(sym_path)
    assert os.path.exists(lab_path)
    assert os.path.exists(cond_path)

    with open(sym_path, "r", encoding="utf-8") as f:
        sym_count = len(list(csv.DictReader(f)))
    with open(lab_path, "r", encoding="utf-8") as f:
        lab_count = len(list(csv.DictReader(f)))
    with open(cond_path, "r", encoding="utf-8") as f:
        cond_count = len(list(csv.DictReader(f)))

    assert sym_count == 57, f"Expected 57 symptom mappings, found {sym_count}"
    assert lab_count == 13, f"Expected 13 lab mappings, found {lab_count}"
    assert cond_count == 20, f"Expected 20 condition mappings, found {cond_count}"
    assert sym_count + lab_count + cond_count == 90
