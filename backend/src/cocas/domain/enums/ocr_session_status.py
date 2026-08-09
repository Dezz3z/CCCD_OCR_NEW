"""OCR session lifecycle status (§4.3.3 `OcrSessionStatus`, `ocr_session.status`)."""
from enum import Enum


class OcrSessionStatus(str, Enum):
    """Lifecycle status of a single OCR extraction session."""

    CREATED = "CREATED"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    NEEDS_REUPLOAD = "NEEDS_REUPLOAD"
    NEEDS_MANUAL_ASSIGN = "NEEDS_MANUAL_ASSIGN"
    FAILED = "FAILED"
    CONFIRMED = "CONFIRMED"
    CONSUMED = "CONSUMED"
    CANCELLED = "CANCELLED"

    @property
    def is_terminal(self) -> bool:
        """True once the session can no longer transition (used by `ck_ocr_session__completed_has_time`)."""
        return self in {
            OcrSessionStatus.COMPLETED,
            OcrSessionStatus.COMPLETED_WITH_WARNINGS,
            OcrSessionStatus.FAILED,
            OcrSessionStatus.CANCELLED,
            OcrSessionStatus.CONSUMED,
        }
