"""Template entity (§4.4.8 `contract_template`).

`party_schema` and `contract_fields` are kept as plain `list`/`dict` JSON-like
structures rather than a fully-typed value object — their grammar (§4.5) is
only interpreted by the Wizard (P4) and `TemplateInspector`; modeling it
strictly here would be speculative structure ahead of need (P-10).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from cocas.domain.exceptions import BusinessRuleViolation


@dataclass(slots=True)
class Template:
    """A registered contract template (`contract_template`), independent of any
    specific uploaded `.docx` — see `TemplateVersion` for the actual file.
    """

    id: uuid.UUID
    code: str
    name: str
    party_schema: list[dict[str, object]]
    contract_no_pattern: str
    export_name_pattern: str
    created_at: datetime
    description: str | None = None
    category: str | None = None
    active_version_id: uuid.UUID | None = None
    party_schema_version: int = 1
    contract_fields: list[dict[str, object]] = field(default_factory=list)
    suppressed_variables: list[str] = field(default_factory=list)
    contract_no_seq: int = 0
    requires_images: bool = False
    is_active: bool = True
    sort_order: int = 100
    updated_at: datetime | None = None
    deleted_at: datetime | None = None

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def activate_version(self, version_id: uuid.UUID, now: datetime) -> None:
        self.active_version_id = version_id
        self.updated_at = now

    def next_contract_sequence(self) -> int:
        """Increment and return the per-template contract-number counter.

        ⭐ Caller must hold a row lock (`SELECT ... FOR UPDATE`) for the
        duration of this call — see `ContractNumberGenerator` (§12 Domain
        Services) and DB-09.
        """
        self.contract_no_seq += 1
        return self.contract_no_seq

    def deactivate(self, now: datetime) -> None:
        self.is_active = False
        self.updated_at = now

    def soft_delete(self, now: datetime) -> None:
        if self.is_deleted:
            raise BusinessRuleViolation("Mẫu hợp đồng đã bị xoá trước đó.", code="ALREADY_DELETED")
        self.deleted_at = now
        self.is_active = False
        self.updated_at = now
