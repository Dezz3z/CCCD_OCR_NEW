"""`card_image` (§4.4.1) — uploaded CCCD photos. Hard-deleted (not soft) on purge (P-05)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from cocas.infrastructure.persistence.models.base import Base, CreatedAtMixin, UuidPkMixin


class CardImageModel(UuidPkMixin, CreatedAtMixin, Base):
    __tablename__ = "card_image"
    __table_args__ = (
        CheckConstraint("side_confidence IS NULL OR side_confidence BETWEEN 0 AND 1", name="side_confidence_range"),
        CheckConstraint("width_px BETWEEN 320 AND 12000", name="width_range"),
        CheckConstraint("height_px BETWEEN 320 AND 12000", name="height_range"),
        CheckConstraint("size_bytes <= 10485760", name="max_size"),
        CheckConstraint("quality_score IS NULL OR quality_score BETWEEN 0 AND 1", name="quality_score_range"),
        Index(
            "uq_card_image__uploader_sha",
            "uploaded_by",
            "sha256",
            unique=True,
            postgresql_where="purged_at IS NULL",
        ),
        Index("ix_card_image__purge_scan", "created_at", postgresql_where="purged_at IS NULL"),
    )

    uploaded_by: Mapped[str] = mapped_column(String(64), nullable=False)
    document_type_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("document_type.id", ondelete="RESTRICT"), nullable=False
    )
    side_hint: Mapped[str] = mapped_column(String(10), nullable=False)
    side_resolved: Mapped[str | None] = mapped_column(String(10), nullable=True)
    side_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    sha256: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    vault_path: Mapped[str] = mapped_column(String(300), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(50), nullable=False)
    width_px: Mapped[int] = mapped_column(Integer, nullable=False)
    height_px: Mapped[int] = mapped_column(Integer, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    exif_orientation: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_flags: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    purged_at: Mapped[datetime | None] = mapped_column(nullable=True)
    purge_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
