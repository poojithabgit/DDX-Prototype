"""
src/ingestion/validator.py

JSON Schema validator for Finding objects produced by the extractor.
Converts each Pydantic Finding to a dict and validates it against
the finding.schema.json — both validations must pass.

Keeping this separate from the extractor means validation logic can
be tested independently and reused by the Case Graph (Stage 3).
"""

from __future__ import annotations

import json
import os

import jsonschema
from jsonschema import Draft202012Validator

from src.common.errors import SchemaValidationError
from src.common.models import Finding

# Load schema once at import time
_SCHEMA_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "schemas", "finding.schema.json"
)
with open(_SCHEMA_PATH, encoding="utf-8") as _f:
    _FINDING_SCHEMA: dict = json.load(_f)

_FINDING_VALIDATOR = Draft202012Validator(_FINDING_SCHEMA)


def validate_finding(finding: Finding) -> None:
    """Validate a Finding against finding.schema.json.

    Raises SchemaValidationError if the JSON Schema check fails.
    Pydantic already validated the Python-level types when the Finding
    was constructed; this validator adds the extra JSON Schema constraints
    (enum lists, additionalProperties: false, etc.).
    """
    # model_dump produces a plain dict; mode='json' serialises enums to their values
    # exclude_none=True omits optional fields that are None (like confidence)
    # which JSON Schema does not permit to be null when optional.
    data = finding.model_dump(mode="json", exclude_none=True)
    try:
        _FINDING_VALIDATOR.validate(data)
    except jsonschema.ValidationError as exc:
        raise SchemaValidationError("Finding", exc.message) from exc


def validate_all(findings: list[Finding]) -> tuple[list[Finding], list[dict]]:
    """Validate every Finding in a list.

    Returns:
        (valid_findings, schema_failures)
        schema_failures: list of dicts with finding_id and reason
    """
    valid:    list[Finding] = []
    failures: list[dict]   = []

    for finding in findings:
        try:
            validate_finding(finding)
            valid.append(finding)
        except SchemaValidationError as exc:
            failures.append({
                "finding_id": finding.id,
                "encounter_id": finding.encounter_id,
                "reason": str(exc),
            })

    return valid, failures
