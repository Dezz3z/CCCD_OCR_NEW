"""ContractDocument entity (§4.4.12) — ⭐ D2.1: at most one `.docx` per contract."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from cocas.domain.enums.doc_type import DocType
from cocas.domain.exceptions import BusinessRuleViolation


@dataclass(slots=True)
class ContractDocument:
    """The rendered file behind a contract — where it lives and what it hashes to.

    ⚠️ `file_path` is a **Vault-relative** reference (`{category}/{yyyy}/{mm}/
    {dd}/{uuid}.enc`, §12.13), never the user-facing `export_name`. The two
    are separate on purpose: a Vault filename that carried a customer's name
    would leak it to anyone listing the directory, and would put
    user-controlled text into a path (§9.14.3).
    """

    id: uuid.UUID
    contract_id: uuid.UUID
    file_path: str
    file_sha256: bytes
    file_size_bytes: int
    generator: str
    generation_ms: int
    created_at: datetime
    doc_type: DocType = DocType.DOCX
    download_count: int = 0
    last_downloaded_at: datetime | None = None

    def __post_init__(self) -> None:
        if len(self.file_sha256) != 32:
            raise BusinessRuleViolation(
                "SHA-256 của tài liệu phải dài đúng 32 byte.",
                code="INVALID_DOCUMENT_HASH",
                field="file_sha256",
            )
        if self.file_size_bytes <= 0:
            raise BusinessRuleViolation(
                "Tài liệu rỗng không phải là hợp đồng hợp lệ.",
                code="EMPTY_DOCUMENT",
                field="file_size_bytes",
            )

    def record_download(self, now: datetime) -> None:
        """⭐ Counted for the Diagnostics screen, not for access control."""
        self.download_count += 1
        self.last_downloaded_at = now
