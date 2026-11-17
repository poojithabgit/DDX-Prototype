"""
src/common/models.py

Pydantic v2 data models for every type used in the five JSON schemas.
These models are the shared language between all modules.

Design rules (from docs/INTERFACES.md):
 - Data that crosses a module boundary MUST be a Pydantic model from here.
 - No module defines its own copy of these models.
 - Field names, types and enumerations match the schemas exactly.
 - model_config uses populate_by_name=True so alias names work alongside
   Python names. No field is silently coerced in a way the schema forbids.

Beginner note:
  Pydantic is a library that checks your data as soon as you create an object.
  If you try to create a Finding with trust_tier="X", Pydantic will immediately
  raise a clear error message instead of storing a corrupt value.
"""

from __future__ import annotations

from typing import Any, List, Optional, Union
from pydantic import BaseModel, Field, model_validator

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


# ===========================================================================
# Shared sub-objects
# ===========================================================================

class ClinicalCode(BaseModel):
    """A terminology code (SNOMED CT, LOINC, or LOCAL).

    Maps to the 'code' sub-object in finding.schema.json and the
    'concept' $def in likelihood-ratio.schema.json.
    """
    model_config = {"extra": "forbid"}  # mirrors additionalProperties: false

    system: str = Field(..., description="SNOMED-CT, LOINC, or LOCAL")
    code: str
    display: str

    @model_validator(mode="after")
    def system_must_be_known(self) -> "ClinicalCode":
        allowed = {"SNOMED-CT", "LOINC", "LOCAL"}
        if self.system not in allowed:
            raise ValueError(f"code.system must be one of {allowed}, got '{self.system}'")
        return self


class ReferenceRange(BaseModel):
    """Normal numeric limits from the local lab or the KB.

    Stored with the finding so the clinician can see exactly which
    thresholds were used to classify the value.
    """
    model_config = {"extra": "forbid"}

    low: Optional[float] = None
    high: Optional[float] = None
    source: str = Field(..., description="'local-lab' or 'kb-default'")

    @model_validator(mode="after")
    def source_must_be_known(self) -> "ReferenceRange":
        if self.source not in {"local-lab", "kb-default"}:
            raise ValueError(
                f"reference_range.source must be 'local-lab' or 'kb-default', got '{self.source}'"
            )
        return self


class Provenance(BaseModel):
    """Full traceability record for one clinical fact.

    Every finding must have a Provenance. A fact without a source is rejected.
    Maps to the 'provenance' sub-object in finding.schema.json.
    """
    model_config = {"extra": "forbid"}

    source_id: str = Field(..., description="ID of the source document or record")
    source_type: SourceType
    fhir_resource: Optional[str] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    quote: Optional[str] = Field(
        None,
        description="Exact text from the source, character for character"
    )
    speaker: Optional[Speaker] = None
    timestamp_in_source: Optional[str] = None
    extractor: str = Field(..., description="name@version of the extracting component")
    method: ExtractionMethod


class Confirmation(BaseModel):
    """Clinician review record for a finding.

    pending  → all T6 findings start here (needs checkpoint 1 review).
    confirmed/edited/rejected → after clinician acts.
    not_required → reserved for T1–T2 findings from trusted deterministic sources
                   (not used in this synthetic prototype).
    """
    model_config = {"extra": "forbid"}

    status: ConfirmationStatus
    by: Optional[str] = None
    at: Optional[str] = Field(None, description="ISO 8601 datetime of review")
    original_value: Optional[Any] = Field(
        None, description="Value before a clinician edit"
    )


# ===========================================================================
# Finding — the core data type for Stage 2
# ===========================================================================

class Finding(BaseModel):
    """One clinical fact about a patient.

    This is the most important model in Stage 2. It represents a single
    observation, symptom, vital sign, lab result or history item.

    Maps exactly to finding.schema.json.
    Required fields (from schema): id, encounter_id, kind, code, assertion,
                                   provenance, trust_tier, confirmation.
    """
    model_config = {"extra": "forbid"}

    id: str = Field(..., description="Unique within the encounter, e.g. f-ENC000001-sym-0001")
    encounter_id: str
    kind: FindingKind
    code: ClinicalCode
    original_text: Optional[str] = Field(
        None, description="The words as written or spoken in the source"
    )
    value: Optional[Union[float, str, bool]] = None
    unit: Optional[str] = Field(None, description="UCUM unit")
    reference_range: Optional[ReferenceRange] = None
    interpretation: Optional[Interpretation] = None
    assertion: Assertion
    onset_day: Optional[int] = Field(
        None, description="Days relative to presentation. 0 = today, negative = past."
    )
    duration_days: Optional[float] = None
    trend: Optional[str] = Field(
        None, description="rising, falling, stable, single_value, or unknown"
    )
    finding_group: Optional[str] = None
    provenance: Provenance
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    trust_tier: TrustTier
    confirmation: Confirmation

    @model_validator(mode="after")
    def trend_must_be_known_value(self) -> "Finding":
        allowed = {"rising", "falling", "stable", "single_value", "unknown", None}
        if self.trend not in allowed:
            raise ValueError(
                f"trend must be one of {allowed}, got '{self.trend}'"
            )
        return self

    def is_confirmed(self) -> bool:
        """Return True if this finding has been confirmed by a clinician.
        Only confirmed findings (T1–T5) can affect diagnostic scores.
        """
        return self.confirmation.status in {
            ConfirmationStatus.CONFIRMED,
            ConfirmationStatus.EDITED,
            ConfirmationStatus.NOT_REQUIRED,
        }

    def can_move_scores(self) -> bool:
        """Return True if this finding is allowed to change Bayesian probabilities.
        T6 findings cannot move scores regardless of their confirmation status.
        """
        return self.trust_tier != TrustTier.T6 and self.is_confirmed()


# ===========================================================================
# Hypothesis
# ===========================================================================

class LRTrailEntry(BaseModel):
    """One likelihood ratio applied during scoring.
    Stored in the hypothesis for the 'why?' audit panel.
    """
    model_config = {"extra": "forbid"}

    finding_or_group: str
    lr: float = Field(..., gt=0)
    kb_entry: str
    verdict_id: str


class Hypothesis(BaseModel):
    """One candidate diagnosis with its scoring trail.
    Maps to hypothesis.schema.json.
    Required fields: id, encounter_id, name, origin, must_not_miss, status, round.
    """
    model_config = {"extra": "forbid"}

    id: str
    encounter_id: str
    code: Optional[ClinicalCode] = None
    icd10: Optional[str] = None
    name: str
    origin: List[HypothesisOrigin] = Field(..., min_length=1)
    must_not_miss: bool
    rationale: Optional[str] = None
    prior: Optional[float] = Field(None, ge=0.0, le=1.0)
    p_raw: Optional[float] = Field(None, ge=0.0, le=1.0)
    p_calibrated: Optional[float] = Field(None, ge=0.0, le=1.0)
    band: Optional[Band] = None
    lr_trail: Optional[List[LRTrailEntry]] = None
    status: HypothesisStatus
    ruled_out_by: Optional[str] = None
    kb_version: Optional[str] = None
    calibration_version: Optional[str] = None
    round: int = Field(..., ge=0)


# ===========================================================================
# Verdict
# ===========================================================================

class CitationRef(BaseModel):
    """An exact passage from the evidence corpus, checked character-for-character."""
    model_config = {"extra": "forbid"}

    source: str
    chunk_id: str
    quote: str


class Verdict(BaseModel):
    """The result of one verifier checking one claim.
    Maps to verdict.schema.json.
    Required fields: verdict_id, claim_id, result, deterministic, verifier, reason.
    """
    model_config = {"extra": "forbid"}

    verdict_id: str
    claim_id: str
    claim_type: Optional[ClaimType] = None
    result: VerdictResult
    kb_entry: Optional[str] = None
    rule_id: Optional[str] = None
    citation: Optional[CitationRef] = None
    deterministic: bool
    verifier: str
    model: Optional[str] = None
    reason: str
    unverifiable_reason: Optional[str] = None
    latency_ms: Optional[int] = Field(None, ge=0)

    @model_validator(mode="after")
    def support_refute_needs_evidence(self) -> "Verdict":
        if self.result in {VerdictResult.SUPPORT, VerdictResult.REFUTE}:
            has_evidence = (
                (self.kb_entry is not None) or
                (self.rule_id is not None) or
                (self.citation is not None)
            )
            if not has_evidence:
                raise ValueError(
                    "A SUPPORT or REFUTE verdict must have kb_entry, rule_id, or citation."
                )
        return self


# ===========================================================================
# Claim
# ===========================================================================

class Claim(BaseModel):
    """A proposed link between a finding and a hypothesis, to be verified.
    Maps to claim.schema.json.
    Required fields: claim_id, encounter_id, type, proposed_by, round.
    """
    model_config = {"extra": "forbid"}

    claim_id: str
    encounter_id: str
    type: ClaimType
    finding_id: Optional[str] = None
    hypothesis_id: Optional[str] = None
    test_code: Optional[str] = None
    proposed_relation: Optional[str] = None
    proposed_by: str
    round: int = Field(..., ge=0)

    @model_validator(mode="after")
    def proposed_relation_values(self) -> "Claim":
        if self.proposed_relation not in {"supports", "refutes", None}:
            raise ValueError(
                f"proposed_relation must be 'supports', 'refutes', or null; "
                f"got '{self.proposed_relation}'"
            )
        return self


# ===========================================================================
# LREntry (Likelihood Ratio Knowledge-Base entry)
# ===========================================================================

class LREntrySource(BaseModel):
    """Publication or data source for a likelihood ratio."""
    model_config = {"extra": "forbid"}

    type: LRSourceType
    citation: str
    doi: Optional[str] = None


class ValidIllnessDays(BaseModel):
    """Day range on which a test's LR is valid."""
    from_day: int = Field(..., alias="from")
    to_day: int   = Field(..., alias="to")
    model_config = {"populate_by_name": True}


class LREntry(BaseModel):
    """One entry in the clinical knowledge base linking a finding to a disease.
    Maps to likelihood-ratio.schema.json.
    Required fields: id, disease, finding, population, source, quality,
                     reviewed_by, version.
    At least one of lr_positive, lr_negative, or (sensitivity + specificity)
    must be present.
    """
    model_config = {"extra": "forbid", "populate_by_name": True}

    id: str
    disease: ClinicalCode
    finding: ClinicalCode
    finding_group: Optional[str] = None
    is_group_combined: bool = False
    lr_positive: Optional[float] = Field(None, gt=0)
    lr_negative: Optional[float] = Field(None, gt=0)
    sensitivity: Optional[float] = Field(None, ge=0.0, le=1.0)
    specificity: Optional[float] = Field(None, ge=0.0, le=1.0)
    valid_illness_days: Optional[ValidIllnessDays] = None
    population: str
    source: LREntrySource
    quality: LRQuality
    reviewed_by: List[str] = Field(..., min_length=2)
    version: str
    notes: Optional[str] = None

    @model_validator(mode="after")
    def must_have_lr_or_sn_sp(self) -> "LREntry":
        has_lr_pos = self.lr_positive is not None
        has_lr_neg = self.lr_negative is not None
        has_sn_sp  = (self.sensitivity is not None and self.specificity is not None)
        if not (has_lr_pos or has_lr_neg or has_sn_sp):
            raise ValueError(
                "LREntry must have lr_positive, lr_negative, or both sensitivity and specificity."
            )
        return self


# ===========================================================================
# Case Graph Nodes & Event Models (docs/04-case-graph.md & docs/INTERFACES.md)
# ===========================================================================

class PatientContext(BaseModel):
    """Patient clinical and demographic context (04-case-graph.md section 1)."""
    model_config = {"extra": "forbid"}

    patient_id: str
    age: Optional[int] = Field(None, ge=0, le=130)
    sex: Optional[str] = None
    pregnancy_status: Optional[str] = None
    region: Optional[str] = None
    month: Optional[str] = None
    occupation: Optional[str] = None
    comorbidities: List[str] = Field(default_factory=list)


class Edge(BaseModel):
    """A directed relationship in the Case Graph (04-case-graph.md section 2).

    Edge types:
      supports, refutes, contradicts, derived_from, discriminates,
      verified_by, rules_out, recommends.
    """
    model_config = {"extra": "forbid"}

    id: str
    encounter_id: str
    type: str = Field(..., description="supports, refutes, contradicts, derived_from, discriminates, verified_by, rules_out, recommends")
    src: str = Field(..., description="Source node id")
    dst: str = Field(..., description="Destination node id")
    data: Optional[dict[str, Any]] = None
    version: int = Field(1, ge=1)


class Event(BaseModel):
    """An immutable, append-only event recording one change to the Case Graph.

    Follows docs/04-case-graph.md section 4.
    """
    model_config = {"extra": "forbid"}

    event_id: str
    encounter_id: str
    sequence: int = Field(..., ge=1, description="Strict 1-based monotonically increasing per-encounter index")
    at: str = Field(..., description="ISO 8601 timestamp")
    actor: str = Field(..., description="Component or actor name@version")
    type: str = Field(..., description="Event type, e.g. FINDING_ADDED, FINDING_CONFIRMED, HYPOTHESIS_ADDED, etc.")
    target: Optional[str] = Field(None, description="Target entity ID (finding_id, hypothesis_id, etc.)")
    payload: dict[str, Any] = Field(default_factory=dict, description="Event data payload")
    before: Optional[dict[str, Any]] = None
    after: Optional[dict[str, Any]] = None
    because: Optional[List[str]] = None
    round: Optional[int] = Field(None, ge=0)

