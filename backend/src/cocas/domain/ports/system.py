"""Clock & id-generation ports — ports 16–17 of 18.

Both exist so domain logic never reaches for `datetime.now()` or `uuid4()`
directly. That is what makes time- and id-dependent behaviour testable
(`FrozenClock`, `SequentialIdGenerator`) and keeps P-09 Determinism
enforceable rather than aspirational.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class IClock(Protocol):
    """⭐ Port 16 — the only sanctioned source of "now".

    Implementations: `SystemClock` (production) · `FrozenClock` (tests).
    """

    def now(self) -> datetime:
        """Current instant, timezone-aware and in UTC (DB-12)."""
        ...

    def today(self) -> date:
        """Current date in the user's local timezone (for `contract_date`)."""
        ...


@runtime_checkable
class IIdGenerator(Protocol):
    """⭐ Port 17 — the only sanctioned source of entity ids.

    Implementations: `Uuid7Generator` (production) · `SequentialIdGenerator` (tests).

    ⭐ UUIDv7 (DB-01): time-prefixed, so ids sort roughly chronologically —
    good for B-tree locality — while still not leaking record counts.
    """

    def new_id(self) -> uuid.UUID: ...
