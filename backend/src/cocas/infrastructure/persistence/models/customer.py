"""`customer` (§4.4.6).

⭐ `_enc` columns hold AES-256-GCM ciphertext; `_bidx` columns hold the
deterministic blind-index token used for equality lookups without
decryption (DB-06). Encrypt/decrypt/blind-index all happen in the
repository (`SqlAlchemyCustomerRepository`, task #9) — this model only
knows column shapes, never plaintext PII.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Index,
    LargeBinary,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from cocas.domain.enums.data_quality import DataQuality
from cocas.domain.value_objects.issue_place import BO_CONG_AN, CUC_CANH_SAT_QLHC_TTXH
from cocas.infrastructure.persistence.models.base import (
    Base,
    CreatedAtMixin,
    CreatedByMixin,
    UuidPkMixin,
)

_DATA_QUALITY_VALUES = tuple(q.value for q in DataQuality)


class CustomerModel(CreatedByMixin, UuidPkMixin, CreatedAtMixin, Base):
    __tablename__ = "customer"
    __table_args__ = (
        CheckConstraint(
            f"issue_place IN ('{BO_CONG_AN}', '{CUC_CANH_SAT_QLHC_TTXH}')",
            name="issue_place_valid",
        ),
        CheckConstraint(
            "(no_expiry AND expiry_date IS NULL) OR (NOT no_expiry AND expiry_date IS NOT NULL)",
            name="expiry_logic",
        ),
        CheckConstraint("expiry_date IS NULL OR issue_date <= expiry_date", name="date_order"),
        CheckConstraint(f"data_quality IN {_DATA_QUALITY_VALUES}", name="data_quality_valid"),
        Index(
            "uq_customer__id_number", "id_number_bidx", unique=True, postgresql_where="deleted_at IS NULL"
        ),
        Index(
            "uq_customer__securities_account",
            "securities_account_bidx",
            unique=True,
            postgresql_where="deleted_at IS NULL AND securities_account_bidx IS NOT NULL",
        ),
        Index("ix_customer__phone_bidx", "phone_bidx"),
        Index("ix_customer__email_bidx", "email_bidx"),
        Index(
            "ix_customer__name_trgm",
            "full_name_search",
            postgresql_using="gin",
            postgresql_ops={"full_name_search": "gin_trgm_ops"},
        ),
        Index("ix_customer__created", "created_at", postgresql_where="deleted_at IS NULL"),
    )

    ocr_session_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    full_name_search: Mapped[str] = mapped_column(String(150), nullable=False)
    id_number_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    id_number_bidx: Mapped[bytes] = mapped_column(LargeBinary(16), nullable=False)
    id_number_masked: Mapped[str] = mapped_column(String(20), nullable=False)
    date_of_birth_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    birth_year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(10), nullable=True)
    issue_place: Mapped[str] = mapped_column(String(80), nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    no_expiry: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    phone: Mapped[str] = mapped_column(String(15), nullable=False)
    phone_bidx: Mapped[bytes] = mapped_column(LargeBinary(16), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    email_bidx: Mapped[bytes] = mapped_column(LargeBinary(16), nullable=False)
    address_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    securities_account_no: Mapped[str | None] = mapped_column(String(20), nullable=True)
    securities_account_bidx: Mapped[bytes | None] = mapped_column(LargeBinary(16), nullable=True)
    securities_account_opened_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    province_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    data_quality: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)
