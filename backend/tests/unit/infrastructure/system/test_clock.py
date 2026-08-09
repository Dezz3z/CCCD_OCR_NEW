"""Unit tests for `SystemClock` (Port 16 production implementation)."""
from __future__ import annotations

from datetime import UTC, datetime

from cocas.infrastructure.system.clock import SystemClock


class TestSystemClock:
    def test_now_is_tz_aware_utc(self) -> None:
        now = SystemClock().now()
        assert now.tzinfo is not None
        assert now.utcoffset() == UTC.utcoffset(None)

    def test_now_is_close_to_wall_clock(self) -> None:
        before = datetime.now(UTC)
        now = SystemClock().now()
        after = datetime.now(UTC)
        assert before <= now <= after

    def test_today_matches_now_date(self) -> None:
        clock = SystemClock()
        assert clock.today() == clock.now().astimezone().date()
