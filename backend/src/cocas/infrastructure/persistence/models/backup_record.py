"""`backup_record` (§4.4.18)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from cocas.domain.enums.backup_status import BackupStatus
from cocas.infrastructure.persistence.models.base import Base, CreatedAtMixin, UuidPkMixin, sql_in

_BACKUP_STATUS_VALUES = tuple(s.value for s in BackupStatus)


class BackupRecordModel(UuidPkMixin, CreatedAtMixin, Base):
    __tablename__ = "backup_record"
    __table_args__ = (CheckConstraint(sql_in("status", _BACKUP_STATUS_VALUES), name="status_valid"),)

    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trigger_type: Mapped[str] = mapped_column(String(15), nullable=False)
    # ⭐ Exception to the "always relative" Vault path rule (§4.4.18) — the
    # user picks this location via a native file dialog.
    file_path: Mapped[str] = mapped_column(String(400), nullable=False)
    file_sha256: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    customer_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    contract_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    image_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    app_version: Mapped[str] = mapped_column(String(30), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(30), nullable=False)
    is_encrypted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(15), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(nullable=True)
