"""`IClock` (Port 16) production implementation."""
from __future__ import annotations

from datetime import UTC, date, datetime


class SystemClock:
    """Wraps the OS clock — the only place `datetime.now()` may be called outside tests."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def today(self) -> date:
        return datetime.now(UTC).astimezone().date()
