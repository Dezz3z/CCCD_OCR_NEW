"""`SqlAlchemyBankDirectoryRepository` — the seeded bank list (§4.4.17).

Read-only reference data with no Domain entity, for the same reason
`document_type` has none: it is a lookup table with no invariants of its own.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cocas.domain.value_objects._vn_text import nfc_upper, strip_diacritics
from cocas.infrastructure.persistence.models.bank_directory import BankDirectoryModel


@dataclass(frozen=True, slots=True)
class BankEntry:
    code: str
    short_name: str
    full_name: str
    bin: str
    account_min_len: int
    account_max_len: int


class SqlAlchemyBankDirectoryRepository:
    """Lists and searches `bank_directory`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(self, query: str | None = None, limit: int = 50) -> list[BankEntry]:
        """Active banks, optionally filtered by a free-text fragment.

        ⭐ Matching happens in Python on a diacritic-stripped, upper-cased
        form, not in SQL. §5.4 step 12 searches `"ngoai thuong"` and must find
        `Ngoại thương`; `ILIKE` in PostgreSQL under the `C` collation this
        cluster uses would not, and adding `unaccent` would put a Vietnamese
        text rule in the database where the rest of them live in
        `_vn_text`. The table holds ~10–50 rows, so the whole scan is cheaper
        than the extension.
        """
        statement = (
            select(BankDirectoryModel)
            .where(BankDirectoryModel.is_active.is_(True))
            .order_by(BankDirectoryModel.sort_order, BankDirectoryModel.short_name)
        )
        rows = (await self._session.execute(statement)).scalars().all()
        entries = [
            BankEntry(
                code=row.code,
                short_name=row.short_name,
                full_name=row.full_name,
                bin=row.bin,
                account_min_len=row.account_min_len,
                account_max_len=row.account_max_len,
            )
            for row in rows
        ]
        if not query:
            return entries[:limit]

        needle = _fold(query)
        matched = [
            entry
            for entry in entries
            if needle in _fold(entry.short_name)
            or needle in _fold(entry.full_name)
            or needle in _fold(entry.code)
        ]
        return matched[:limit]


def _fold(value: str) -> str:
    return strip_diacritics(nfc_upper(value))
