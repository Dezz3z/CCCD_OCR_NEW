"""`bank_directory` (§4.4.15) — ~50-row seed, referenced only softly from `bank_account`."""
from __future__ import annotations

from sqlalchemy import Boolean, Integer, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from cocas.infrastructure.persistence.models.base import Base


class BankDirectoryModel(Base):
    __tablename__ = "bank_directory"

    code: Mapped[str] = mapped_column(String(10), primary_key=True)
    short_name: Mapped[str] = mapped_column(String(50), nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    bin: Mapped[str] = mapped_column(String(6), nullable=False)
    account_min_len: Mapped[int] = mapped_column(Integer, nullable=False)
    account_max_len: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=100)
