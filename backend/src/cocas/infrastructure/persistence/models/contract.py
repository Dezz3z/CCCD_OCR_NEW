"""`contract` (§4.4.10) — ⭐ the only table with an optimistic-lock `version` column (DB-09)."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from cocas.domain.enums.contract_status import ContractStatus
from cocas.infrastructure.persistence.models.base import (
    Base,
    CreatedAtMixin,
    CreatedByMixin,
    UuidPkMixin,
)

_STATUS_VALUES = tuple(s.value for s in ContractStatus)


class ContractModel(CreatedByMixin, UuidPkMixin, CreatedAtMixin, Base):
    __tablename__ = "contract"
    __table_args__ = (
        UniqueConstraint("contract_no", name="uq_contract__no"),
        CheckConstraint(
            "status <> 'VOIDED' OR (void_reason IS NOT NULL AND voided_at IS NOT NULL)",
            name="void_has_reason",
        ),
        CheckConstraint("supersedes_id IS NULL OR supersedes_id <> id", name="no_self_supersede"),
        CheckConstraint(f"status IN {_STATUS_VALUES}", name="status_valid"),
        Index("ix_contract__customer", "primary_customer_id", "created_at"),
        Index("ix_contract__status_created", "status", "created_at"),
        Index("ix_contract__export_name", "export_name"),
    )

    contract_no: Mapped[str] = mapped_column(String(60), nullable=False)
    export_name: Mapped[str] = mapped_column(String(220), nullable=False)
    primary_customer_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("customer.id", ondelete="RESTRICT"), nullable=False
    )
    template_version_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("template_version.id", ondelete="RESTRICT"), nullable=False
    )
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("contract.id", ondelete="SET NULL"), nullable=True
    )
    revision_no: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    party_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(25), nullable=False)
    render_snapshot_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    snapshot_sha256: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    extra_variables: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    contract_date: Mapped[date] = mapped_column(Date, nullable=False)
    void_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(nullable=True)
    voided_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)
