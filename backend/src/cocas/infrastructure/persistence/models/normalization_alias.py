"""`normalization_alias` (§4.4.14) — feeds `IssuePlaceNormalizer` tiers 2-4."""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, Index, SmallInteger, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from cocas.infrastructure.persistence.models.base import Base, CreatedAtMixin, UuidPkMixin


class NormalizationAliasModel(UuidPkMixin, CreatedAtMixin, Base):
    __tablename__ = "normalization_alias"
    __table_args__ = (
        Index(
            "uq_normalization_alias",
            "document_type_id",
            "field_key",
            "alias_normalized",
            unique=True,
            postgresql_where="alias_normalized IS NOT NULL",
        ),
        CheckConstraint(
            "(match_tier = 4 AND keywords IS NOT NULL) OR (match_tier < 4 AND alias_normalized IS NOT NULL)",
            name="tier4",
        ),
        CheckConstraint("match_tier BETWEEN 1 AND 4", name="tier_range"),
    )

    document_type_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("document_type.id", ondelete="CASCADE"), nullable=False
    )
    field_key: Mapped[str] = mapped_column(String(30), nullable=False)
    alias_normalized: Mapped[str | None] = mapped_column(String(200), nullable=True)
    canonical_value: Mapped[str] = mapped_column(String(200), nullable=False)
    match_tier: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    keywords: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    assigned_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
