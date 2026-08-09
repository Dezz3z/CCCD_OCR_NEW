"""Contract entity (§4.4.10 `contract`).

⭐ DB-03 Bất biến: once `status == COMPLETED`, only `status`, `void_reason`,
`voided_at`, `voided_by`, `updated_at`, `version` may change. This entity
enforces that by exposing state changes **only** through the methods below
(`void`, `supersede`) — there is no generic setter for business fields once
completed. `version` is `IVersionedEntity`'s optimistic-lock column — the
**only** table in v1.0 that has one (DB-09).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol, runtime_checkable

from cocas.domain.enums.contract_status import ContractStatus
from cocas.domain.exceptions import BusinessRuleViolation

MIN_VOID_REASON_LENGTH = 10

_ALLOWED_TRANSITIONS: dict[ContractStatus, frozenset[ContractStatus]] = {
    ContractStatus.DRAFT: frozenset({ContractStatus.GENERATING}),
    ContractStatus.GENERATING: frozenset(
        {ContractStatus.DOCX_READY, ContractStatus.GENERATION_FAILED}
    ),
    ContractStatus.DOCX_READY: frozenset(
        {ContractStatus.PDF_CONVERTING, ContractStatus.COMPLETED}
    ),
    ContractStatus.PDF_CONVERTING: frozenset(
        {ContractStatus.COMPLETED, ContractStatus.PDF_FAILED}
    ),
    ContractStatus.GENERATION_FAILED: frozenset({ContractStatus.GENERATING}),
    ContractStatus.PDF_FAILED: frozenset({ContractStatus.PDF_CONVERTING}),
    ContractStatus.COMPLETED: frozenset(),
    ContractStatus.SUPERSEDED: frozenset(),
    ContractStatus.VOIDED: frozenset(),
}

# Void is allowed from every status except the two already-terminal ones.
_VOIDABLE_STATUSES = frozenset(ContractStatus) - {ContractStatus.VOIDED, ContractStatus.SUPERSEDED}


@runtime_checkable
class IVersionedEntity(Protocol):
    """Marker for entities carrying an optimistic-lock `version` column.

    v1.0: only `Contract` implements this (§12.14) — `IWriteRepository.update()`
    only accepts `expected_version` for entities matching this protocol.
    """

    version: int


@dataclass(slots=True)
class Contract:
    """A generated contract document's business record."""

    id: uuid.UUID
    contract_no: str
    export_name: str
    primary_customer_id: uuid.UUID
    template_version_id: uuid.UUID
    created_by: str
    contract_date: date
    created_at: datetime
    updated_at: datetime
    status: ContractStatus = ContractStatus.DRAFT
    supersedes_id: uuid.UUID | None = None
    revision_no: int = 1
    party_count: int = 1
    snapshot_sha256: bytes | None = None
    extra_variables: dict[str, object] | None = None
    void_reason: str | None = None
    voided_at: datetime | None = None
    voided_by: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    version: int = 1

    def __post_init__(self) -> None:
        if self.supersedes_id == self.id:
            raise BusinessRuleViolation(
                "Hợp đồng không thể tự thay thế chính nó.", code="SELF_SUPERSEDE"
            )

    def _transition(self, new_status: ContractStatus, now: datetime) -> None:
        allowed = _ALLOWED_TRANSITIONS[self.status]
        if new_status not in allowed:
            raise BusinessRuleViolation(
                f"Không thể chuyển hợp đồng từ '{self.status.value}' sang '{new_status.value}'.",
                code="INVALID_CONTRACT_TRANSITION",
            )
        self.status = new_status
        self.updated_at = now
        self.version += 1

    def mark_generating(self, now: datetime) -> None:
        self._transition(ContractStatus.GENERATING, now)

    def mark_docx_ready(self, snapshot_sha256: bytes, now: datetime) -> None:
        self.snapshot_sha256 = snapshot_sha256
        self._transition(ContractStatus.DOCX_READY, now)

    def mark_pdf_converting(self, now: datetime) -> None:
        self._transition(ContractStatus.PDF_CONVERTING, now)

    def mark_completed(self, now: datetime) -> None:
        self._transition(ContractStatus.COMPLETED, now)
        self.error_code = None
        self.error_message = None

    def mark_generation_failed(self, error_code: str, error_message: str, now: datetime) -> None:
        self.error_code = error_code
        self.error_message = error_message
        self._transition(ContractStatus.GENERATION_FAILED, now)

    def mark_pdf_failed(self, error_code: str, error_message: str, now: datetime) -> None:
        self.error_code = error_code
        self.error_message = error_message
        self._transition(ContractStatus.PDF_FAILED, now)

    def retry_generation(self, now: datetime) -> None:
        self._transition(ContractStatus.GENERATING, now)

    def void(self, reason: str, by: str, now: datetime) -> None:
        if self.status not in _VOIDABLE_STATUSES:
            raise BusinessRuleViolation(
                f"Không thể huỷ hợp đồng ở trạng thái '{self.status.value}'.",
                code="CONTRACT_NOT_VOIDABLE",
            )
        if len(reason) < MIN_VOID_REASON_LENGTH:
            raise BusinessRuleViolation(
                f"Lý do huỷ phải có ít nhất {MIN_VOID_REASON_LENGTH} ký tự.",
                code="VOID_REASON_TOO_SHORT",
                field="void_reason",
            )
        self.void_reason = reason
        self.voided_by = by
        self.voided_at = now
        self.status = ContractStatus.VOIDED
        self.updated_at = now
        self.version += 1

    def supersede(self, now: datetime) -> None:
        """Mark this contract as replaced by a newer revision."""
        if self.status != ContractStatus.COMPLETED:
            raise BusinessRuleViolation(
                "Chỉ hợp đồng đã hoàn tất mới có thể bị thay thế.",
                code="CONTRACT_NOT_SUPERSEDABLE",
            )
        self.status = ContractStatus.SUPERSEDED
        self.updated_at = now
        self.version += 1

    @property
    def is_completed(self) -> bool:
        return self.status == ContractStatus.COMPLETED

    @property
    def is_locked_for_business_edits(self) -> bool:
        """⭐ DB-03: once True, only status/void_*/updated_at/version may change."""
        return self.status in {
            ContractStatus.COMPLETED,
            ContractStatus.SUPERSEDED,
            ContractStatus.VOIDED,
        }
