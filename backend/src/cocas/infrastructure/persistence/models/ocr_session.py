"""`ocr_session` (§4.4.2) — one OCR extraction attempt over a front+back image pair."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from cocas.domain.enums.ocr_session_status import OcrSessionStatus
from cocas.infrastructure.persistence.models.base import (
    Base,
    CreatedAtMixin,
    CreatedByMixin,
    UuidPkMixin,
)

_STATUS_VALUES = tuple(s.value for s in OcrSessionStatus)


class OcrSessionModel(CreatedByMixin, UuidPkMixin, CreatedAtMixin, Base):
    __tablename__ = "ocr_session"
    __table_args__ = (
        CheckConstraint("front_image_id <> back_image_id", name="different_images"),
        CheckConstraint(
            "status NOT IN ('COMPLETED','COMPLETED_WITH_WARNINGS','FAILED') OR completed_at IS NOT NULL",
            name="completed_has_time",
        ),
        CheckConstraint(f"status IN {_STATUS_VALUES}", name="status_valid"),
        CheckConstraint("overall_confidence IS NULL OR overall_confidence BETWEEN 0 AND 1", name="confidence_range"),
        Index("ix_ocr_session__user_created", "created_by", "created_at"),
        Index(
            "ix_ocr_session__active",
            "status",
            postgresql_where="status IN ('QUEUED', 'PROCESSING')",
        ),
    )

    document_type_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("document_type.id", ondelete="RESTRICT"), nullable=False
    )
    front_image_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        # ⭐ Explicit names: two FKs from this table target `card_image`, and
        # the naming_convention default (fk_<table>__<referred_table>) would
        # collapse both to the same name — caught by a real `CREATE TABLE`
        # against PostgreSQL (asyncpg.DuplicateObjectError), not by metadata
        # introspection alone.
        ForeignKey("card_image.id", ondelete="RESTRICT", name="fk_ocr_session__card_image_front"),
        nullable=False,
    )
    back_image_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("card_image.id", ondelete="RESTRICT", name="fk_ocr_session__card_image_back"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    party_key: Mapped[str | None] = mapped_column(String(40), nullable=True, default="holder")
    party_index: Mapped[int | None] = mapped_column(SmallInteger, nullable=True, default=0)
    auto_swapped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    overall_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    engine_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    engine_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    preprocessing_profile: Mapped[str | None] = mapped_column(String(50), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(40), nullable=False)
    diagnostics: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
