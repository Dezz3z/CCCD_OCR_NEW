"""`SqlAlchemyCardImageRepository` — implements `IReadRepository`/`IWriteRepository` for `CardImage`."""
from __future__ import annotations

from sqlalchemy import select

from cocas.domain.entities.card_image import CardImage
from cocas.domain.enums.card_side import CardSide
from cocas.domain.value_objects.confidence_score import ConfidenceScore
from cocas.infrastructure.persistence.models.card_image import CardImageModel
from cocas.infrastructure.persistence.repositories._base import SqlAlchemyRepository


class SqlAlchemyCardImageRepository(SqlAlchemyRepository[CardImage, CardImageModel]):
    model = CardImageModel

    async def find_by_sha256(self, digest: bytes) -> CardImage | None:
        """The image with this content, if one is already stored (`COCAS-3007`).

        ⭐ Lets the caller answer *before* encrypting 900 KB into the Vault and
        then deleting it again when the UNIQUE index refuses the row. The
        constraint is still the authority — two simultaneous uploads of the
        same photo can both pass this check — but the common case stops paying
        for a write nobody keeps.
        """
        statement = select(self.model).where(self.model.sha256 == digest)
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return self._to_domain(row) if row is not None else None

    def _to_domain(self, row: CardImageModel) -> CardImage:
        return CardImage(
            id=row.id,
            uploaded_by=row.uploaded_by,
            document_type_id=row.document_type_id,
            side_hint=CardSide(row.side_hint),
            vault_path=row.vault_path,
            mime_type=row.mime_type,
            width_px=row.width_px,
            height_px=row.height_px,
            size_bytes=row.size_bytes,
            sha256=row.sha256,
            created_at=row.created_at,
            side_resolved=CardSide(row.side_resolved) if row.side_resolved else None,
            side_confidence=ConfidenceScore(row.side_confidence) if row.side_confidence is not None else None,
            exif_orientation=row.exif_orientation,
            quality_score=ConfidenceScore(row.quality_score) if row.quality_score is not None else None,
            quality_flags=list(row.quality_flags) if row.quality_flags else [],
            thumbnail_path=row.thumbnail_path,
            purged_at=row.purged_at,
            purge_reason=row.purge_reason,
        )

    def _apply_to_row(self, entity: CardImage, row: CardImageModel) -> None:
        row.id = entity.id
        row.uploaded_by = entity.uploaded_by
        row.document_type_id = entity.document_type_id
        row.side_hint = entity.side_hint.value
        row.side_resolved = entity.side_resolved.value if entity.side_resolved else None
        row.side_confidence = entity.side_confidence.value if entity.side_confidence else None
        row.sha256 = entity.sha256
        row.vault_path = entity.vault_path
        row.mime_type = entity.mime_type
        row.width_px = entity.width_px
        row.height_px = entity.height_px
        row.size_bytes = entity.size_bytes
        row.exif_orientation = entity.exif_orientation
        row.quality_score = entity.quality_score.value if entity.quality_score else None
        row.quality_flags = list(entity.quality_flags)
        row.thumbnail_path = entity.thumbnail_path
        row.purged_at = entity.purged_at
        row.purge_reason = entity.purge_reason
        row.created_at = entity.created_at
