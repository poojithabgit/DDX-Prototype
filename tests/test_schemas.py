"""
Test suite to validate all prototype JSON Schemas against JSON Schema Draft 2020-12.
Covers:
- finding.schema.json
- hypothesis.schema.json
- likelihood-ratio.schema.json
- verdict.schema.json
- claim.schema.json (newly created from docs/INTERFACES.md)
"""

import os
import json
import pytest
import jsonschema
from jsonschema import Draft202012Validator

SCHEMAS_DIR = os.path.join(os.path.dirname(__file__), "..", "schemas")

SCHEMA_FILES = [
    "finding.schema.json",
    "hypothesis.schema.json",
    "likelihood-ratio.schema.json",
    "verdict.schema.json",
    "claim.schema.json",
]

def load_schema(filename: str) -> dict:
    path = os.path.join(SCHEMAS_DIR, filename)
    assert os.path.exists(path), f"Schema file not found: {path}"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

@pytest.mark.parametrize("filename", SCHEMA_FILES)
def test_schema_validity(filename: str):
    """Every schema must be a valid JSON Schema Draft 2020-12."""
    schema = load_schema(filename)
    Draft202012Validator.check_schema(schema)

def test_claim_schema_fields():
    """Verify claim.schema.json conforms to docs/INTERFACES.md Section 2."""
    claim_schema = load_schema("claim.schema.json")
    required = claim_schema.get("required", [])
    expected_required = ["claim_id", "encounter_id", "type", "proposed_by", "round"]
    for r in expected_required:
        assert r in required, f"claim.schema.json must require '{r}'"

    claim_types = claim_schema["properties"]["type"]["enum"]
    expected_types = [
        "FINDING_DISEASE_LINK",
        "LAB_INTERPRETATION",
        "DRUG_CAUSE",
        "TEST_SAFETY",
        "FACT_CONSISTENCY",
        "IMAGING_FINDING",
        "MNM_STATUS",
    ]
    assert set(claim_types) == set(expected_types), "ClaimType enum mismatch"

def test_claim_schema_validation():
    """Test valid and invalid claim instances."""
    claim_schema = load_schema("claim.schema.json")
    validator = Draft202012Validator(claim_schema)

    # Valid claim
    valid_claim = {
        "claim_id": "c-0031",
        "encounter_id": "ENC000001",
        "type": "FINDING_DISEASE_LINK",
        "finding_id": "f-0007",
        "hypothesis_id": "h-dengue",
        "test_code": None,
        "proposed_relation": "supports",
        "proposed_by": "proposer@llm-A:prompt-v3",
        "round": 1,
    }
    validator.validate(valid_claim)

    # Invalid claim: missing required 'round'
    invalid_claim = {
        "claim_id": "c-0031",
        "encounter_id": "ENC000001",
        "type": "FINDING_DISEASE_LINK",
        "proposed_by": "test",
    }
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(invalid_claim)

def test_finding_schema_validation():
    """Test valid finding instance against finding.schema.json."""
    finding_schema = load_schema("finding.schema.json")
    validator = Draft202012Validator(finding_schema)

    valid_finding = {
        "id": "f-0001",
        "encounter_id": "ENC000001",
        "kind": "symptom",
        "code": {
            "system": "SNOMED-CT",
            "code": "62315008",
            "display": "Diarrhea (finding)",
        },
        "original_text": "diarrhea",
        "value": None,
        "unit": None,
        "reference_range": None,
        "interpretation": "abnormal",
        "assertion": "present",
        "onset_day": -7,
        "duration_days": 7.0,
        "trend": "unknown",
        "finding_group": None,
        "provenance": {
            "source_id": "NOTE-PT000001",
            "source_type": "clinical_note",
            "fhir_resource": None,
            "char_start": 0,
            "char_end": 8,
            "quote": "diarrhea",
            "speaker": "patient",
            "timestamp_in_source": None,
            "extractor": "synthetic-template-v1",
            "method": "rules",
        },
        "confidence": 1.0,
        "trust_tier": "T1",
        "confirmation": {
            "status": "confirmed",
            "by": "Dr. Lead",
            "at": "2026-04-08T10:00:00Z",
            "original_value": None,
        },
    }
    validator.validate(valid_finding)
