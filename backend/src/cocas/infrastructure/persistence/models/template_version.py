"""`template_version` (§4.4.9) — ⭐ never deleted, only archived (P-09 determinism)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from cocas.domain.enums.template_validation_status import TemplateValidationStatus
from cocas.infrastructure.persistence.models.base import (
    Base,
    CreatedAtMixin,
    CreatedByMixin,
    UuidPkMixin,
)

_VALIDATION_STATUS_VALUES = tuple(s.value for s in TemplateValidationStatus)


class TemplateVersionModel(CreatedByMixin, UuidPkMixin, CreatedAtMixin, Base):
    __tablename__ = "template_version"
    __table_args__ = (
        UniqueConstraint("template_id", "version_no", name="uq_template_version__no"),
        CheckConstraint("file_size_bytes <= 20971520", name="max_size"),
        CheckConstraint(f"validation_status IN {_VALIDATION_STATUS_VALUES}", name="validation_status_valid"),
    )

    template_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("contract_template.id", ondelete="RESTRICT"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str] = mapped_column(String(300), nullable=False)
    file_sha256: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    declared_variables: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    required_variables: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    optional_variables: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    unknown_variables: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    richtext_variables: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    has_loops: Mapped[bool] = mapped_column(Boolean, nullable=False)
    has_conditionals: Mapped[bool] = mapped_column(Boolean, nullable=False)
    validation_status: Mapped[str] = mapped_column(String(15), nullable=False)
    validation_report: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    changelog: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(nullable=True)
