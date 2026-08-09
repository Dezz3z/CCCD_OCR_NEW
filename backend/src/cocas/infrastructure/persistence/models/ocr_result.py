"""`ocr_result` (§4.4.3) — 1:0..1 with `ocr_session` (a FAILED session has none)."""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, LargeBinary, SmallInteger
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from cocas.infrastructure.persistence.models.base import Base, CreatedAtMixin, UuidPkMixin


class OcrResultModel(UuidPkMixin, CreatedAtMixin, Base):
    __tablename__ = "ocr_result"
    __table_args__ = (
        CheckConstraint(
            "mrz_corrections_applied IS NULL OR mrz_corrections_applied BETWEEN 0 AND 3",
            name="corrections_range",
        ),
    )

    ocr_session_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("ocr_session.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    qr_available: Mapped[bool] = mapped_column(Boolean, nullable=False)
    qr_raw_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    mrz_available: Mapped[bool] = mapped_column(Boolean, nullable=False)
    mrz_raw_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    mrz_checksum_valid: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    mrz_corrections_applied: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    raw_engine_output_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    channel_summary: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    validation_report: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    cross_check_flags: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
