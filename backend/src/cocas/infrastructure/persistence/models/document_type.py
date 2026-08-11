"""`document_type` (§4.4.13) — the row that makes adding a new ID type (NFR-10) a data change, not a code change."""
from __future__ import annotations

from sqlalchemy import Boolean, Float, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from cocas.infrastructure.persistence.models.base import Base, CreatedAtMixin, UuidPkMixin


class DocumentTypeModel(UuidPkMixin, CreatedAtMixin, Base):
    __tablename__ = "document_type"

    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    field_schema: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    zone_map: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    anchor_patterns: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    identity_markers: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    """⭐ Phrases printed on this generation and no other (§7.4.7).

    Deliberately NOT derived from `anchor_patterns`: both generations declare
    `Full name`, `Date of birth` and `BỘ CÔNG AN` as anchors, so counting
    anchor hits would rank photos by legibility rather than by card generation.
    Read by `MarkerDocumentTypeSelector` (Port 19).
    """
    has_qr: Mapped[bool] = mapped_column(Boolean, nullable=False)
    has_mrz: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_ocr_supported: Mapped[bool] = mapped_column(Boolean, nullable=False)
    expected_aspect_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
