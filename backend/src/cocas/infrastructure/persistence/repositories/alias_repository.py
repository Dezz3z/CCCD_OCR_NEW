"""`SqlAlchemyAliasRepository` — Port 10, the cached alias lookup (§12.5, §4.4.14).

⭐ **This repository does not take an `AsyncSession`, and that is the whole
design.** Every other repository binds to the Unit of Work's session because it
serves one Use Case's transaction. This one serves `IssuePlaceNormalizer`, a
Domain Service built **once** in the Composition Root and living inside
`ExtractionPipeline` for the process's whole lifetime. Handing it a session
would mean either:

* pinning a long-lived singleton to a session that a Use Case will close under
  it — a `MissingGreenlet`/`IllegalStateChangeError` the first time a second
  request arrives; or
* enlisting a read of 19 rows of reference data into the caller's business
  transaction, so that rolling back a contract also rolls back… nothing, while
  holding the reference rows under that transaction's snapshot the whole time.

So it takes the session **factory** and opens its own short read for a cache
miss. §12.5's port docstring already asked for this ("read-mostly with an
in-memory cache"); this is what that costs.

⭐ **Both methods read the same cache.** `find_by_alias` is deliberately *not*
a `WHERE alias_normalized = :x` query: two code paths reaching the same table
through different SQL is how the exact-match tier and the fuzzy tier end up
disagreeing about which rows exist. One loader, one cache, two views of it.

⚠️ **`alias_normalized` is NULL for tier-4 rows** (they carry `keywords`
instead — see the `tier4` CHECK on the table). A lookup must never match NULL
against NULL: `find_by_alias(..., "")` asking for "the row with no alias" would
otherwise return a keyword row and assign its canonical value at full
confidence.
"""
from __future__ import annotations

import asyncio
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cocas.domain.exceptions import DatabaseUnavailableError
from cocas.domain.ports.persistence import AliasRecord
from cocas.infrastructure.persistence.models.document_type import DocumentTypeModel
from cocas.infrastructure.persistence.models.normalization_alias import NormalizationAliasModel

_CacheKey = tuple[str, str]


class SqlAlchemyAliasRepository:
    """Port 10 — `normalization_alias` rows, loaded once per (type, field).

    The cache is unbounded on purpose: the key space is
    `document_type` by `field_key`, which is 2 by 6 at its largest in v1.0. An
    eviction policy here would be structure without a payer (P-10).
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._cache: dict[_CacheKey, tuple[AliasRecord, ...]] = {}
        # ⭐ One loader at a time per process. Without it, the first extraction
        # of a cold start issues N identical queries — one per concurrent
        # field lookup — and each one pays the full round trip.
        self._lock = asyncio.Lock()

    async def find_by_alias(
        self, document_type_code: str, field_key: str, alias_normalized: str
    ) -> AliasRecord | None:
        """Tier 2 — exact match on a curated alias. `None` when nothing matches."""
        if not alias_normalized:
            # See the module docstring: an empty needle must not find the
            # tier-4 rows, whose `alias_normalized` is NULL.
            return None
        for record in await self.list_active(document_type_code, field_key):
            if record.alias_normalized == alias_normalized:
                return record
        return None

    async def list_active(
        self, document_type_code: str, field_key: str
    ) -> Sequence[AliasRecord]:
        """Every active alias row for this (document type, field), cached."""
        key = (document_type_code, field_key)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        async with self._lock:
            # Someone may have loaded it while we waited for the lock.
            cached = self._cache.get(key)
            if cached is not None:
                return cached
            records = await self._load(document_type_code, field_key)
            self._cache[key] = records
            return records

    def invalidate(self, document_type_code: str | None = None, field_key: str | None = None) -> None:
        """Drop cached rows after `POST`/`DELETE /reference/aliases` (§5.2 #49–51).

        Called with no arguments it clears everything. ⭐ Cache invalidation is
        exposed rather than inferred from a TTL: an admin who adds an alias to
        fix a misread card expects the next scan to use it, and a TTL turns
        that into "sometime in the next N minutes".
        """
        if document_type_code is None and field_key is None:
            self._cache.clear()
            return
        for key in [
            k
            for k in self._cache
            if (document_type_code is None or k[0] == document_type_code)
            and (field_key is None or k[1] == field_key)
        ]:
            del self._cache[key]

    async def _load(self, document_type_code: str, field_key: str) -> tuple[AliasRecord, ...]:
        statement = (
            select(NormalizationAliasModel)
            .join(
                DocumentTypeModel,
                DocumentTypeModel.id == NormalizationAliasModel.document_type_id,
            )
            .where(
                DocumentTypeModel.code == document_type_code,
                NormalizationAliasModel.field_key == field_key,
                NormalizationAliasModel.is_active.is_(True),
            )
            # Deterministic order so a fuzzy tie between two aliases resolves
            # the same way on every machine and every run.
            .order_by(
                NormalizationAliasModel.match_tier,
                NormalizationAliasModel.canonical_value,
                NormalizationAliasModel.id,
            )
        )
        try:
            async with self._session_factory() as session:
                rows = (await session.execute(statement)).scalars().all()
        except OperationalError as exc:  # pragma: no cover - needs a dead DB
            raise DatabaseUnavailableError("Không kết nối được cơ sở dữ liệu.") from exc
        return tuple(_to_record(row) for row in rows)


def _to_record(row: NormalizationAliasModel) -> AliasRecord:
    return AliasRecord(
        id=row.id,
        field_key=row.field_key,
        canonical_value=row.canonical_value,
        match_tier=row.match_tier,
        assigned_confidence=row.assigned_confidence,
        alias_normalized=row.alias_normalized,
        keywords=tuple(row.keywords or ()),
    )
