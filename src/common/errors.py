"""
src/common/errors.py

Named exceptions for the Medagents prototype.
Using specific exception names (instead of a generic "Exception") means
the calling code can catch exactly the error it expects, and
accidental programming errors propagate rather than being silently swallowed.
"""


class MedagentsError(Exception):
    """Base class for all Medagents prototype errors."""


class ProvenanceMissingError(MedagentsError):
    """Raised when a fact has no traceable source record.

    Every clinical finding MUST link to its exact source.
    Facts without provenance are rejected, not stored.
    """


class SchemaValidationError(MedagentsError):
    """Raised when a generated object fails JSON Schema validation.

    Wraps the underlying jsonschema.ValidationError with context
    about which object failed and why.
    """
    def __init__(self, object_type: str, details: str) -> None:
        self.object_type = object_type
        self.details = details
        super().__init__(f"Schema validation failed for {object_type}: {details}")


class UnsupportedUnitError(MedagentsError):
    """Raised when a unit cannot be safely compared or converted.

    We never perform unit conversions unless the mapping is explicitly
    verified. If the reported unit and UCUM unit cannot be matched,
    this error is raised and the interpretation is set to not_applicable.
    """
    def __init__(self, reported_unit: str, ucum_unit: str) -> None:
        self.reported_unit = reported_unit
        self.ucum_unit = ucum_unit
        super().__init__(
            f"Cannot safely compare unit '{reported_unit}' with UCUM unit '{ucum_unit}'."
        )


class ReferenceRangeMissingError(MedagentsError):
    """Raised when a numeric lab result has no valid reference range.

    Without a reference range from the local lab or KB, we cannot
    classify a value as low/normal/high. The finding is kept, but
    interpretation is set to not_applicable.
    """


class RejectedFindingError(MedagentsError):
    """Raised when a finding must be quarantined rather than stored.

    Reasons include: missing provenance, impossible value, span check
    failure, or the source is a benchmark/illustrative dataset.
    """
    def __init__(self, reason: str, source_id: str = "") -> None:
        self.reason = reason
        self.source_id = source_id
        super().__init__(f"Finding rejected [{source_id}]: {reason}")


class InvalidValueError(MedagentsError):
    """Raised when a numeric value is outside physiologically possible limits."""
    def __init__(self, field: str, value: str, limit_description: str) -> None:
        self.field = field
        self.value = value
        super().__init__(
            f"Value '{value}' for '{field}' is outside possible limits: {limit_description}"
        )


class PermissionDenied(MedagentsError):
    """Raised when a component attempts a write operation outside its permissions.

    See docs/04-case-graph.md section 5. Logged as a bug; never retried.
    """
    def __init__(self, component: str, action: str, details: str = "") -> None:
        self.component = component
        self.action = action
        self.details = details
        msg = f"Permission denied for component '{component}' performing '{action}'."
        if details:
            msg += f" {details}"
        super().__init__(msg)


class StaleVersion(MedagentsError):
    """Raised when an append or update specifies an expected_version that does not match current version.

    The caller must re-read the graph view and retry.
    """
    def __init__(self, encounter_id: str, expected_version: int, current_version: int) -> None:
        self.encounter_id = encounter_id
        self.expected_version = expected_version
        self.current_version = current_version
        super().__init__(
            f"Stale version for encounter '{encounter_id}': "
            f"expected {expected_version}, but current version is {current_version}."
        )


class ImplausibleValue(MedagentsError):
    """Raised when a clinical value or unit is impossible or corrupt."""


class CaseGraphError(MedagentsError):
    """Base error for Case Graph operational errors."""


class EventReplayError(CaseGraphError):
    """Raised when an event log cannot be replayed or corrupts graph state."""

