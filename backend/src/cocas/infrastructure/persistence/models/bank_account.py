"""`bank_account` (§4.4.7)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, LargeBinary, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from cocas.infrastructure.persistence.models.base import Base, CreatedAtMixin, UuidPkMixin


class BankAccountModel(UuidPkMixin, CreatedAtMixin, Base):
    __tablename__ = "bank_account"
    __table_args__ = (
        Index(
            "uq_bank_account__one_primary",
            "customer_id",
            unique=True,
            postgresql_where="is_primary AND deleted_at IS NULL",
        ),
        Index(
            "uq_bank_account__no_dup",
            "customer_id",
            "account_number_bidx",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("customer.id", ondelete="CASCADE"), nullable=False
    )
    account_number_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    account_number_bidx: Mapped[bytes] = mapped_column(LargeBinary(16), nullable=False)
    account_number_masked: Mapped[str] = mapped_column(String(25), nullable=False)
    bank_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    bank_name: Mapped[str] = mapped_column(String(150), nullable=False)
    branch: Mapped[str] = mapped_column(String(150), nullable=False)
    account_holder_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)
