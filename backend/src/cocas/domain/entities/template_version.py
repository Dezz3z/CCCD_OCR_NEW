"""TemplateVersion entity (§4.4.9 `template_version`)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from cocas.domain.enums.template_validation_status import TemplateValidationStatus
from cocas.domain.exceptions import BusinessRuleViolation

MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024


@dataclass(slots=True)
class TemplateVersion:
    """One uploaded `.docx` revision of a `Template`.

    ⭐ Never deleted — `archived_at` marks it superseded but the row (and the
    file, per DB-04/P-09 determinism) is kept so an old contract can always
    be regenerated identically.
    """

    id: uuid.UUID
    template_id: uuid.UUID
    version_no: int
    file_path: str
    file_sha256: bytes
    file_size_bytes: int
    original_filename: str
    declared_variables: list[str]
    required_variables: list[str]
    optional_variables: list[str]
    validation_status: TemplateValidationStatus
    created_by: str
    created_at: datetime
    unknown_variables: list[str] = field(default_factory=list)
    richtext_variables: list[str] = field(default_factory=list)
    has_loops: bool = False
    has_conditionals: bool = False
    validation_report: dict[str, object] = field(default_factory=dict)
    changelog: str | None = None
    archived_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.file_size_bytes > MAX_FILE_SIZE_BYTES:
            raise BusinessRuleViolation(
                f"File mẫu không được vượt quá {MAX_FILE_SIZE_BYTES} byte.",
                code="TEMPLATE_FILE_TOO_LARGE",
            )
        if self.version_no < 1:
            raise BusinessRuleViolation(
                "Số phiên bản mẫu phải bắt đầu từ 1.", code="INVALID_VERSION_NO"
            )

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    @property
    def is_usable(self) -> bool:
        """Whether this version can be selected to generate a new contract."""
        return not self.is_archived and self.validation_status != TemplateValidationStatus.INVALID

    def archive(self, now: datetime) -> None:
        if self.is_archived:
            raise BusinessRuleViolation(
                "Phiên bản mẫu đã được lưu trữ trước đó.", code="ALREADY_ARCHIVED"
            )
        self.archived_at = now
