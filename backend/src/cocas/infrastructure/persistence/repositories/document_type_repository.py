"""`SqlAlchemyDocumentTypeRepository` — the active card generations (§4.4.13).

Returns `DocumentTypeSpec` (a Port record), not an entity: `document_type` has
no behaviour and no invariants of its own — it is the data that makes adding a
new ID type a row rather than a code change (NFR-10). Wrapping it in a Domain
entity would add a layer whose only job is to copy nine fields.

⭐ **Order is a tie-break, never an answer.** `ExtractionPipeline` documents its
`doc_types` argument as "most likely first", and it would be easy to read that
as "the first one is what this card probably is". It is not: which generation a
card belongs to is decided at S7 by `MarkerDocumentTypeSelector` from the text
actually printed on it (§7.4.7, finding #37). This repository therefore returns
a **deterministic** order rather than a clever one — seed order, oldest first —
so that two machines running the same photo take the same path, and so nothing
downstream is tempted to treat position as evidence.

Same session-factory shape as `SqlAlchemyAliasRepository`, for the same reason:
its consumer is a long-lived pipeline, not one Use Case's transaction.
"""
from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cocas.domain.exceptions import DatabaseUnavailableError
from cocas.domain.ports.ocr import DocumentTypeSpec
from cocas.infrastructure.persistence.models.document_type import DocumentTypeModel


class SqlAlchemyDocumentTypeRepository:
    """Reads `document_type`, cached — it changes only when a migration runs."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._cache: tuple[DocumentTypeSpec, ...] | None = None

    async def list_extractable(self) -> Sequence[DocumentTypeSpec]:
        """Active types the OCR pipeline can actually extract through.

        ⚠️ Filters on **both** `is_active` and `is_ocr_supported`. A type with
        `is_ocr_supported = false` has no usable `zone_map`; handing it to the
        pipeline as a candidate would let the generation selector pick it and
        then extract every field through coordinates that were never
        calibrated — §7.9's confidently-wrong failure, sourced from a config
        flag instead of a photo.
        """
        if self._cache is not None:
            return self._cache

        statement = (
            select(DocumentTypeModel)
            .where(
                DocumentTypeModel.is_active.is_(True),
                DocumentTypeModel.is_ocr_supported.is_(True),
            )
            .order_by(DocumentTypeModel.created_at, DocumentTypeModel.code)
        )
        try:
            async with self._session_factory() as session:
                rows = (await session.execute(statement)).scalars().all()
        except OperationalError as exc:  # pragma: no cover - needs a dead DB
            raise DatabaseUnavailableError("Không kết nối được cơ sở dữ liệu.") from exc

        self._cache = tuple(_to_spec(row) for row in rows)
        return self._cache

    async def get_by_code(self, code: str) -> DocumentTypeSpec | None:
        """One type by `code`, from the same cache as `list_extractable()`."""
        for spec in await self.list_extractable():
            if spec.code == code:
                return spec
        return None

    def invalidate(self) -> None:
        """Drop the cache — for tests and for a migration applied while running."""
        self._cache = None


def _to_spec(row: DocumentTypeModel) -> DocumentTypeSpec:
    return DocumentTypeSpec(
        code=row.code,
        name=row.name,
        field_schema=list(row.field_schema),
        zone_map=dict(row.zone_map),
        anchor_patterns=dict(row.anchor_patterns),
        has_qr=row.has_qr,
        has_mrz=row.has_mrz,
        is_ocr_supported=row.is_ocr_supported,
        expected_aspect_ratio=row.expected_aspect_ratio,
        identity_markers=tuple(row.identity_markers or ()),
    )
