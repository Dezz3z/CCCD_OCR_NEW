"""`ocr_field` (§4.4.4) — ⭐ the table the whole self-improvement loop (§14.7 A1) reads from."""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    LargeBinary,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from cocas.domain.enums.field_key import FieldKey
from cocas.domain.enums.field_source import FieldSource
from cocas.infrastructure.persistence.models.base import Base, UuidPkMixin, sql_in

_FIELD_KEY_VALUES = tuple(k.value for k in FieldKey)
_SOURCE_VALUES = tuple(s.value for s in FieldSource)


class OcrFieldModel(UuidPkMixin, Base):
    __tablename__ = "ocr_field"
    __table_args__ = (
        UniqueConstraint("ocr_result_id", "field_key", name="uq_ocr_field__result_key"),
        CheckConstraint(sql_in("field_key", _FIELD_KEY_VALUES), name="field_key_valid"),
        CheckConstraint(sql_in("source", _SOURCE_VALUES), name="source_valid"),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="confidence_range"),
        # ⭐ 1..5, not 1..4. `IssuePlaceNormalizer` gained a fifth tier on
        # 2026-08-11 (§12.5.1, the opening-letters discriminator) and it is the
        # tier that resolves most real readings — 20 of 20 in the sample. The
        # old bound would have rejected almost every `issue_place` row the
        # pipeline produces, at INSERT time, in a background job.
        CheckConstraint(
            "normalization_tier IS NULL OR normalization_tier BETWEEN 1 AND 5", name="tier_range"
        ),
        Index(
            "ix_ocr_field__corrected", "field_key", "source", postgresql_where="user_corrected"
        ),
    )

    ocr_result_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("ocr_result.id", ondelete="CASCADE"), nullable=False
    )
    field_key: Mapped[str] = mapped_column(String(30), nullable=False)
    raw_value_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    normalized_value_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    final_value_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    source: Mapped[str] = mapped_column(String(10), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False)
    user_corrected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    user_value_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    bbox: Mapped[dict[str, float] | None] = mapped_column(JSONB, nullable=True)
    candidates: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB, nullable=True)
    normalization_tier: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
