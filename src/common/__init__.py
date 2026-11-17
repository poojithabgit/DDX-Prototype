"""
src/common/__init__.py
Package marker. Import shared types and models from here.
"""
from src.common.types import (
    TrustTier,
    Assertion,
    VerdictResult,
    ClaimType,
    FindingKind,
    Interpretation,
    Band,
    ConfirmationStatus,
    HypothesisStatus,
    HypothesisOrigin,
    SourceType,
    ExtractionMethod,
    Speaker,
)
from src.common.models import (
    ClinicalCode,
    ReferenceRange,
    Provenance,
    Confirmation,
    Finding,
    LRTrailEntry,
    Hypothesis,
    CitationRef,
    Verdict,
    Claim,
    LREntrySource,
    ValidIllnessDays,
    LREntry,
    PatientContext,
    Edge,
    Event,
)
from src.common.errors import (
    ProvenanceMissingError,
    SchemaValidationError,
    UnsupportedUnitError,
    ReferenceRangeMissingError,
    RejectedFindingError,
    InvalidValueError,
    PermissionDenied,
    StaleVersion,
    ImplausibleValue,
    CaseGraphError,
    EventReplayError,
)
from src.common.clock import (
    Clock,
    IdFactory,
    SystemClock,
    FixedClock,
    UuidIdFactory,
    DeterministicIdFactory,
)

__all__ = [
    "TrustTier", "Assertion", "VerdictResult", "ClaimType", "FindingKind",
    "Interpretation", "Band", "ConfirmationStatus", "HypothesisStatus",
    "HypothesisOrigin", "SourceType", "ExtractionMethod", "Speaker",
    "ClinicalCode", "ReferenceRange", "Provenance", "Confirmation", "Finding",
    "LRTrailEntry", "Hypothesis", "CitationRef", "Verdict", "Claim",
    "LREntrySource", "ValidIllnessDays", "LREntry",
    "PatientContext", "Edge", "Event",
    "ProvenanceMissingError", "SchemaValidationError", "UnsupportedUnitError",
    "ReferenceRangeMissingError", "RejectedFindingError", "InvalidValueError",
    "PermissionDenied", "StaleVersion", "ImplausibleValue", "CaseGraphError", "EventReplayError",
    "Clock", "IdFactory", "SystemClock", "FixedClock", "UuidIdFactory", "DeterministicIdFactory",
]
