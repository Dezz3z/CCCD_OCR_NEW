"""OcrSession entity (§4.4.2 `ocr_session`)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from cocas.domain.enums.ocr_session_status import OcrSessionStatus
from cocas.domain.exceptions import BusinessRuleViolation
from cocas.domain.value_objects.confidence_score import ConfidenceScore

_TERMINAL_WITH_TIMESTAMP = {
    OcrSessionStatus.COMPLETED,
    OcrSessionStatus.COMPLETED_WITH_WARNINGS,
    OcrSessionStatus.FAILED,
}


@dataclass(slots=True)
class OcrSession:
    """A single OCR extraction attempt over one front+back image pair.

    `party_key`/`party_index` are the ⭐ multi-party hinge (ADR-16) — v1.0
    always uses `"holder"`/`0`, kept so a second party doesn't require a
    schema migration later.
    """

    id: uuid.UUID
    created_by: str
    document_type_id: uuid.UUID
    front_image_id: uuid.UUID
    back_image_id: uuid.UUID
    correlation_id: str
    created_at: datetime
    status: OcrSessionStatus = OcrSessionStatus.CREATED
    party_key: str | None = "holder"
    party_index: int = 0
    auto_swapped: bool = False
    overall_confidence: ConfidenceScore | None = None
    engine_name: str | None = None
    engine_version: str | None = None
    preprocessing_profile: str | None = None
    duration_ms: int | None = None
    diagnostics: dict[str, object] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.front_image_id == self.back_image_id:
            raise BusinessRuleViolation(
                "Ảnh mặt trước và mặt sau không được là cùng một ảnh.",
                code="SAME_FRONT_BACK_IMAGE",
            )
        if self.status in _TERMINAL_WITH_TIMESTAMP and self.completed_at is None:
            raise BusinessRuleViolation(
                "Phiên OCR ở trạng thái kết thúc phải có thời điểm hoàn tất.",
                code="MISSING_COMPLETED_AT",
            )

    def transition_to(
        self,
        status: OcrSessionStatus,
        now: datetime,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Move to a new lifecycle status, stamping `completed_at` if terminal."""
        if self.status.is_terminal:
            raise BusinessRuleViolation(
                f"Phiên OCR đã ở trạng thái kết thúc '{self.status.value}', không thể chuyển tiếp.",
                code="OCR_SESSION_ALREADY_TERMINAL",
            )
        self.status = status
        if status in _TERMINAL_WITH_TIMESTAMP:
            self.completed_at = now
        if error_code is not None:
            self.error_code = error_code
        if error_message is not None:
            self.error_message = error_message
