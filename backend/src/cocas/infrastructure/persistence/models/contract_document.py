"""`contract_document` (§4.4.12) — ⭐ D2.1: at most 1 DOCX per contract.

The `doc_type` column and its unique constraint stay: they are what stops a
second document row being written for the same contract. `page_count` is
gone — it only ever meant "pages of the PDF" (§9.13).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from cocas.domain.enums.doc_type import DocType
from cocas.infrastructure.persistence.models.base import Base, CreatedAtMixin, UuidPkMixin

_DOC_TYPE_VALUES = tuple(t.value for t in DocType)


class ContractDocumentModel(UuidPkMixin, CreatedAtMixin, Base):
    __tablename__ = "contract_document"
    __table_args__ = (
        UniqueConstraint("contract_id", "doc_type", name="uq_contract_document__type"),
        CheckConstraint(f"doc_type IN {_DOC_TYPE_VALUES}", name="doc_type_valid"),
    )

    contract_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("contract.id", ondelete="CASCADE"), nullable=False
    )
    doc_type: Mapped[str] = mapped_column(String(10), nullable=False)
    file_path: Mapped[str] = mapped_column(String(300), nullable=False)
    file_sha256: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    generator: Mapped[str] = mapped_column(String(60), nullable=False)
    generation_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    download_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_downloaded_at: Mapped[datetime | None] = mapped_column(nullable=True)
