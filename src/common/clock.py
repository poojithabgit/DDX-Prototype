"""
src/common/clock.py

Time and ID generation protocols for the Medagents system.

Design rules (from docs/INTERFACES.md section 1.4):
- Time and IDs are injected.
- Pass a Clock and an IdFactory instead of calling datetime.now() or uuid4()
  directly inside reasoning or graph components.
- This ensures replay, audit, and tests give identical, deterministic results.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol
import uuid


class Clock(Protocol):
    """Protocol for providing current timestamps."""
    def now(self) -> datetime:
        """Return the current datetime (must be timezone-aware or ISO-compatible)."""
        ...

    def now_iso(self) -> str:
        """Return current datetime as an ISO-8601 string."""
        ...


class IdFactory(Protocol):
    """Protocol for generating unique identifiers."""
    def next_id(self, prefix: str = "id") -> str:
        """Generate a new unique identifier with an optional prefix."""
        ...


class SystemClock:
    """Default system clock using standard library UTC time."""
    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def now_iso(self) -> str:
        return self.now().isoformat()


class FixedClock:
    """Fixed or controllable clock for deterministic testing and replay."""
    def __init__(self, fixed_time: datetime | str | None = None) -> None:
        if fixed_time is None:
            self._time = datetime(2026, 11, 17, 10, 0, 0, tzinfo=timezone.utc)
        elif isinstance(fixed_time, str):
            self._time = datetime.fromisoformat(fixed_time)
        else:
            self._time = fixed_time

    def set_time(self, new_time: datetime | str) -> None:
        if isinstance(new_time, str):
            self._time = datetime.fromisoformat(new_time)
        else:
            self._time = new_time

    def advance_seconds(self, seconds: float) -> None:
        from datetime import timedelta
        self._time += timedelta(seconds=seconds)

    def now(self) -> datetime:
        return self._time

    def now_iso(self) -> str:
        return self._time.isoformat()


class UuidIdFactory:
    """Default UUID4-based ID factory."""
    def next_id(self, prefix: str = "id") -> str:
        return f"{prefix}-{uuid.uuid4().hex[:8]}"


class DeterministicIdFactory:
    """Sequential deterministic ID factory for tests and replay."""
    def __init__(self, start: int = 1) -> None:
        self._counters: dict[str, int] = {}
        self._default_counter = start

    def next_id(self, prefix: str = "id") -> str:
        count = self._counters.get(prefix, self._default_counter)
        self._counters[prefix] = count + 1
        return f"{prefix}-{count:06d}"
