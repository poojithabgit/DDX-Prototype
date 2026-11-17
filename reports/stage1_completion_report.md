# Stage 1: Workspace Setup & Ingestion Sample — Completion Report

**Project:** Medagents (Agentic Differential Diagnosis System)  
**Workspace:** `C:\Users\DELL\Desktop\prototype of madd`  
**Date:** November 2026  
**Status:** **ALL 11 REQUIREMENTS SATISFIED — 25/25 AUTOMATED TESTS PASSED**

---

## 1. Executive Summary

Stage 1 has successfully established an isolated, self-contained, and fully validated prototype environment inside `C:\Users\DELL\Desktop\prototype of madd`. 

All operations strictly respected the file protection mandate:
- **Zero original files were modified or deleted** in `C:\Users\DELL\Desktop\Mini project\Medagents\medagents`.
- A representative sample of **15 adult patient encounters** (all age $\ge 18$) was extracted across all 11 clinical tables.
- Full CSV and JSON Lines (`.jsonl`) parity was maintained across all tables.
- All 5 JSON schemas—including the newly authored `claim.schema.json`—were verified against JSON Schema Draft 2020-12.
- An automated test suite was constructed and executed with **25/25 passing tests**.

---

## 2. Directories and Files Created

### Folder Structure
```text
C:\Users\DELL\Desktop\prototype of madd\
├── eval/
│   └── golden/
│       └── worked-example.json         # Copied golden fever case (golden-we-001)
├── kb/                                 # Ready for Stage 4 knowledge base files
├── reports/
│   └── stage1_completion_report.md     # This report
├── sample_data/
│   ├── sample_metadata.json            # Sampling audit ledger
│   ├── mappings/                       # Terminology mappings (SNOMED, LOINC, ICD-10)
│   │   ├── conditions_icd10_snomed_mapping.csv
│   │   ├── labs_loinc_mapping.csv
│   │   ├── symptoms_snomed_mapping.csv
│   │   └── terminology_mapping_status.md
│   ├── differential_candidates.csv / .jsonl
│   ├── encounters.csv / .jsonl
│   ├── lab_results.csv / .jsonl
│   ├── medical_history.csv / .jsonl
│   ├── medications.csv / .jsonl
│   ├── patients.csv / .jsonl
│   ├── provenance.csv / .jsonl
│   ├── reference_diagnoses.csv / .jsonl
│   ├── symptoms_normalized.csv / .jsonl
│   ├── timeline.csv / .jsonl
│   └── vitals.csv / .jsonl
├── schemas/
│   ├── claim.schema.json               # Newly created from docs/INTERFACES.md
│   ├── finding.schema.json             # Copied from original repo
│   ├── hypothesis.schema.json          # Copied from original repo
│   ├── likelihood-ratio.schema.json    # Copied from original repo
│   └── verdict.schema.json             # Copied from original repo
├── scripts/
│   └── extract_sample.py               # Deterministic sampling utility
├── src/
│   ├── api/                            # Ready for Stage 5 API
│   ├── common/                         # Ready for Stage 2 Pydantic models
│   ├── graph/                          # Ready for Stage 3 Case Graph
│   ├── ingestion/                      # Ready for Stage 2 Ingestion extractor
│   ├── reasoning/                      # Ready for Stage 4 Bayesian Scorer
│   └── verifiers/                      # Ready for Stage 4 Verifiers
└── tests/
    ├── test_schemas.py                 # Schema validity & claim contract tests
    └── test_stage1_sample.py           # Sample integrity, FKs, parity & safety tests
```

---

## 3. Sampled Cohort Details

- **Number of Sampled Adult Encounters:** 15
- **Number of Sampled Adult Patients:** 15
- **Patient IDs:** `PT000001`, `PT000003`, `PT000004`, `PT000005`, `PT000007`, `PT000008`, `PT000009`, `PT000010`, `PT000011`, `PT000012`, `PT000013`, `PT000014`, `PT000015`, `PT000016`, `PT000017`
  *(Note: IDs `PT000002` and `PT000006` were pediatric patients and were correctly excluded during Phase 3 adult filtering).*
- **Encounter IDs:** `ENC000001`, `ENC000003`, `ENC000004`, `ENC000005`, `ENC000007`, `ENC000008`, `ENC000009`, `ENC000010`, `ENC000011`, `ENC000012`, `ENC000013`, `ENC000014`, `ENC000015`, `ENC000016`, `ENC000017`
- **Age Range:** 18 to 89 years (100% adult; 0 pediatric records).

---

## 4. Tables Included & Row Counts

Every table was generated in both CSV and JSONL formats with exact row count and schema parity:

| # | Table Name | CSV Rows | JSONL Rows | Parity Status | Description |
|---|------------|:--------:|:----------:|:-------------:|-------------|
| 1 | `patients` | 15 | 15 | **PASS** | Patient demographics (age, sex, synthetic name) |
| 2 | `encounters` | 15 | 15 | **PASS** | Encounter metadata (date, type, department) |
| 3 | `symptoms_normalized` | 105 | 105 | **PASS** | Symptoms with SNOMED CT codes and durations |
| 4 | `vitals` | 15 | 15 | **PASS** | Vital signs (Temp, Pulse, BP, RR, SpO2) |
| 5 | `medical_history` | 15 | 15 | **PASS** | Past medical history, allergies, social history |
| 6 | `lab_results` | 32 | 32 | **PASS** | Lab tests with LOINC codes and ref ranges |
| 7 | `medications` | 15 | 15 | **PASS** | Current medications / hydration plans |
| 8 | `differential_candidates` | 60 | 60 | **PASS** | Synthetic demo candidates (flagged non-Bayesian) |
| 9 | `provenance` | 135 | 135 | **PASS** | Source traceability, quotes, and extractors |
| 10 | `timeline` | 30 | 30 | **PASS** | Day index sequence of clinical events |
| 11 | `reference_diagnoses` | 15 | 15 | **PASS** | Benchmark truth (evaluation only) |
| **Total** | **All 11 Tables** | **447** | **447** | **100%** | **Zero orphaned foreign keys** |

---

## 5. Schema Validation & The New `claim.schema.json`

### `claim.schema.json` Implementation
As specified in `docs/INTERFACES.md` Section 2 and `docs/08-verification.md`:
- Required fields: `claim_id`, `encounter_id`, `type`, `proposed_by`, `round`.
- Claim types: `FINDING_DISEASE_LINK`, `LAB_INTERPRETATION`, `DRUG_CAUSE`, `TEST_SAFETY`, `FACT_CONSISTENCY`, `IMAGING_FINDING`, `MNM_STATUS`.
- Direction: `proposed_relation` (`supports`, `refutes`, or `null`).
- Verified compatible with `verdict.schema.json`.

All 5 schemas were tested with `jsonschema.Draft202012Validator` and passed validation.

---

## 6. Safety Policy Invariants

1. **Differential Candidate Scores:**
   - 100% of rows in `sample_data/differential_candidates.csv` have `is_bayesian_probability: False`.
   - `score_interpretation: "synthetic_demo_score_not_calibrated_probability"`.
   - These scores are strictly preserved for demo comparison and will **never** be used in Bayesian calculations.
2. **Reference Diagnoses:**
   - 100% of rows in `sample_data/reference_diagnoses.csv` have `label_role: "synthetic_reference_label_not_clinical_diagnosis"`.
   - These records are strictly isolated for post-hoc evaluation and will **never** be fed into the Case Graph as observed patient findings.
3. **Missing Clinical Duration:**
   - For all absent symptoms (`assertion == "absent"`), durations remain null/empty strings. No zero-imputation was applied.

---

## 7. Automated Test Results

Running `pytest tests -v` generated the following verified output:

```text
tests/test_schemas.py::test_schema_validity[finding.schema.json] PASSED          [  4%]
tests/test_schemas.py::test_schema_validity[hypothesis.schema.json] PASSED       [  8%]
tests/test_schemas.py::test_schema_validity[likelihood-ratio.schema.json] PASSED [ 12%]
tests/test_schemas.py::test_schema_validity[verdict.schema.json] PASSED          [ 16%]
tests/test_schemas.py::test_schema_validity[claim.schema.json] PASSED            [ 20%]
tests/test_schemas.py::test_claim_schema_fields PASSED                           [ 24%]
tests/test_schemas.py::test_claim_schema_validation PASSED                       [ 28%]
tests/test_schemas.py::test_finding_schema_validation PASSED                     [ 32%]
tests/test_stage1_sample.py::test_csv_jsonl_parity[patients] PASSED              [ 36%]
tests/test_stage1_sample.py::test_csv_jsonl_parity[encounters] PASSED            [ 40%]
tests/test_stage1_sample.py::test_csv_jsonl_parity[symptoms_normalized] PASSED   [ 44%]
tests/test_stage1_sample.py::test_csv_jsonl_parity[vitals] PASSED                [ 48%]
tests/test_stage1_sample.py::test_csv_jsonl_parity[medical_history] PASSED      [ 52%]
tests/test_stage1_sample.py::test_csv_jsonl_parity[lab_results] PASSED           [ 56%]
tests/test_stage1_sample.py::test_csv_jsonl_parity[medications] PASSED           [ 60%]
tests/test_stage1_sample.py::test_csv_jsonl_parity[differential_candidates] PASSED [ 64%]
tests/test_stage1_sample.py::test_csv_jsonl_parity[provenance] PASSED            [ 68%]
tests/test_stage1_sample.py::test_csv_jsonl_parity[timeline] PASSED              [ 72%]
tests/test_stage1_sample.py::test_csv_jsonl_parity[reference_diagnoses] PASSED  [ 76%]
tests/test_stage1_sample.py::test_cohort_size_and_adult_filtering PASSED         [ 80%]
tests/test_stage1_sample.py::test_referential_integrity PASSED                   [ 84%]
tests/test_stage1_sample.py::test_missing_clinical_duration_preservation PASSED [ 88%]
tests/test_stage1_sample.py::test_differential_score_safety PASSED               [ 92%]
tests/test_stage1_sample.py::test_reference_diagnosis_policy PASSED              [ 96%]
tests/test_stage1_sample.py::test_terminology_mappings_present PASSED            [100%]

======================== 25 passed, 1 warning in 5.59s ========================
```

---

## 8. Missing Information or Errors

- **Zero errors encountered.**
- The sample cohort is completely self-consistent and fully preserves all foreign key relationships across all 11 tables.
- **Ready for Stage 2:** The prototype has its own schemas, sample data, terminology mappings, and test infrastructure ready for Stage 2 (Pydantic shared models and clinical finding extraction).
