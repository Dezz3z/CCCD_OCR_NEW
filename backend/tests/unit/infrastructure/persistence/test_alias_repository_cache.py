"""`SqlAlchemyAliasRepository` — the caching policy, without a database.

The SQL is covered by `tests/integration/persistence/test_ocr_persistence.py`
against real PostgreSQL. What can only be tested here is the part that is pure
logic and would otherwise be checked by nobody until it misbehaved in
production: how many times a cold cache hits the database, that both public
methods read the same loaded rows, and that a NULL alias can never be matched.

⚠️ `_load` is stubbed rather than mocked at the driver level on purpose. The
question these tests ask is "how often is the database asked, and with what",
and a stub answers it directly; a mocked session would answer it through three
layers of SQLAlchemy behaviour that the integration test already covers.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from cocas.domain.ports.persistence import AliasRecord
from cocas.infrastructure.persistence.repositories.alias_repository import (
    SqlAlchemyAliasRepository,
)

EXACT = AliasRecord(
    id="a1",
    field_key="issue_place",
    canonical_value="BỘ CÔNG AN",
    match_tier=2,
    assigned_confidence=0.95,
    alias_normalized="BO CONG AN",
)
KEYWORD = AliasRecord(
    id="a2",
    field_key="issue_place",
    canonical_value="CỤC CẢNH SÁT QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI",
    match_tier=4,
    assigned_confidence=0.85,
    alias_normalized=None,
    keywords=("CUC", "CANH", "SAT"),
)


class CountingRepository(SqlAlchemyAliasRepository):
    """Replaces the one method that talks to PostgreSQL."""

    def __init__(self, records: tuple[AliasRecord, ...], delay: float = 0.0) -> None:
        super().__init__(session_factory=None)  # type: ignore[arg-type]
        self._records = records
        self._delay = delay
        self.loads: list[tuple[str, str]] = []

    async def _load(self, document_type_code: str, field_key: str) -> tuple[AliasRecord, ...]:
        self.loads.append((document_type_code, field_key))
        if self._delay:
            await asyncio.sleep(self._delay)
        return self._records


def _repo(*records: AliasRecord, **kwargs: Any) -> CountingRepository:
    return CountingRepository(records, **kwargs)


class TestCaching:
    @pytest.mark.asyncio
    async def test_repeated_reads_hit_the_database_once(self) -> None:
        repo = _repo(EXACT, KEYWORD)
        for _ in range(5):
            await repo.list_active("CCCD_CHIP", "issue_place")
        assert repo.loads == [("CCCD_CHIP", "issue_place")]

    @pytest.mark.asyncio
    async def test_different_keys_are_cached_separately(self) -> None:
        repo = _repo(EXACT)
        await repo.list_active("CCCD_CHIP", "issue_place")
        await repo.list_active("CAN_CUOC_2024", "issue_place")
        await repo.list_active("CCCD_CHIP", "full_name")
        assert len(repo.loads) == 3

    @pytest.mark.asyncio
    async def test_concurrent_cold_reads_load_once(self) -> None:
        """⭐ The first extraction of a cold start must not issue N queries."""
        repo = _repo(EXACT, delay=0.01)
        await asyncio.gather(
            *(repo.list_active("CCCD_CHIP", "issue_place") for _ in range(8))
        )
        assert repo.loads == [("CCCD_CHIP", "issue_place")]

    @pytest.mark.asyncio
    async def test_find_by_alias_reads_the_same_cache_as_list_active(self) -> None:
        """One loader, one cache — the two views can never disagree."""
        repo = _repo(EXACT, KEYWORD)
        await repo.list_active("CCCD_CHIP", "issue_place")
        found = await repo.find_by_alias("CCCD_CHIP", "issue_place", "BO CONG AN")
        assert found is EXACT
        assert repo.loads == [("CCCD_CHIP", "issue_place")]


class TestInvalidation:
    @pytest.mark.asyncio
    async def test_invalidate_all_forces_a_reload(self) -> None:
        repo = _repo(EXACT)
        await repo.list_active("CCCD_CHIP", "issue_place")
        repo.invalidate()
        await repo.list_active("CCCD_CHIP", "issue_place")
        assert len(repo.loads) == 2

    @pytest.mark.asyncio
    async def test_invalidate_one_document_type_leaves_the_other_cached(self) -> None:
        repo = _repo(EXACT)
        await repo.list_active("CCCD_CHIP", "issue_place")
        await repo.list_active("CAN_CUOC_2024", "issue_place")
        repo.invalidate(document_type_code="CCCD_CHIP")

        await repo.list_active("CAN_CUOC_2024", "issue_place")
        assert len(repo.loads) == 2  # nothing reloaded

        await repo.list_active("CCCD_CHIP", "issue_place")
        assert len(repo.loads) == 3

    @pytest.mark.asyncio
    async def test_invalidate_by_field_key_only(self) -> None:
        repo = _repo(EXACT)
        await repo.list_active("CCCD_CHIP", "issue_place")
        await repo.list_active("CCCD_CHIP", "full_name")
        repo.invalidate(field_key="issue_place")

        await repo.list_active("CCCD_CHIP", "full_name")
        assert len(repo.loads) == 2

        await repo.list_active("CCCD_CHIP", "issue_place")
        assert len(repo.loads) == 3


class TestNullAliasIsNeverMatched:
    """⚠️ Tier-4 rows have `alias_normalized IS NULL` and keywords instead."""

    @pytest.mark.asyncio
    async def test_empty_needle_finds_nothing(self) -> None:
        repo = _repo(KEYWORD)
        assert await repo.find_by_alias("CCCD_CHIP", "issue_place", "") is None

    @pytest.mark.asyncio
    async def test_a_keyword_row_is_never_returned_by_exact_match(self) -> None:
        repo = _repo(KEYWORD)
        assert await repo.find_by_alias("CCCD_CHIP", "issue_place", "CUC") is None

    @pytest.mark.asyncio
    async def test_but_keyword_rows_are_still_listed(self) -> None:
        """Tier 4 needs them — `list_active` returns every active row."""
        repo = _repo(EXACT, KEYWORD)
        listed = await repo.list_active("CCCD_CHIP", "issue_place")
        assert list(listed) == [EXACT, KEYWORD]

    @pytest.mark.asyncio
    async def test_unknown_alias_returns_none_rather_than_the_first_row(self) -> None:
        repo = _repo(EXACT, KEYWORD)
        assert await repo.find_by_alias("CCCD_CHIP", "issue_place", "KHONG CO") is None
