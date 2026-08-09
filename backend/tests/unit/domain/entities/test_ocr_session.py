"""Tests for OcrSession entity (§4.4.2)."""
import uuid
from datetime import UTC, datetime

import pytest

from cocas.domain.entities.ocr_session import OcrSession
from cocas.domain.enums.ocr_session_status import OcrSessionStatus
from cocas.domain.exceptions import BusinessRuleViolation

NOW = datetime(2026, 8, 9, tzinfo=UTC)


def _make(**overrides: object) -> OcrSession:
    front = uuid.uuid4()
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "created_by": "phthang",
        "document_type_id": uuid.uuid4(),
        "front_image_id": front,
        "back_image_id": uuid.uuid4(),
        "correlation_id": "corr-1",
        "created_at": NOW,
    }
    defaults.update(overrides)
    return OcrSession(**defaults)  # type: ignore[arg-type]


class TestConstruction:
    def test_valid_session_defaults_to_created(self) -> None:
        session = _make()
        assert session.status == OcrSessionStatus.CREATED
        assert session.party_key == "holder"

    def test_same_front_back_image_rejected(self) -> None:
        same_id = uuid.uuid4()
        with pytest.raises(BusinessRuleViolation) as exc_info:
            _make(front_image_id=same_id, back_image_id=same_id)
        assert exc_info.value.code == "SAME_FRONT_BACK_IMAGE"

    def test_terminal_status_without_completed_at_rejected(self) -> None:
        with pytest.raises(BusinessRuleViolation) as exc_info:
            _make(status=OcrSessionStatus.COMPLETED, completed_at=None)
        assert exc_info.value.code == "MISSING_COMPLETED_AT"

    def test_terminal_status_with_completed_at_allowed(self) -> None:
        _make(status=OcrSessionStatus.COMPLETED, completed_at=NOW)


class TestTransition:
    def test_created_to_processing(self) -> None:
        session = _make()
        session.transition_to(OcrSessionStatus.PROCESSING, NOW)
        assert session.status == OcrSessionStatus.PROCESSING
        assert session.completed_at is None

    def test_transition_to_terminal_stamps_completed_at(self) -> None:
        session = _make()
        session.transition_to(OcrSessionStatus.COMPLETED, NOW)
        assert session.completed_at == NOW

    def test_transition_after_terminal_rejected(self) -> None:
        session = _make()
        session.transition_to(OcrSessionStatus.FAILED, NOW)
        with pytest.raises(BusinessRuleViolation) as exc_info:
            session.transition_to(OcrSessionStatus.PROCESSING, NOW)
        assert exc_info.value.code == "OCR_SESSION_ALREADY_TERMINAL"

    def test_transition_records_error(self) -> None:
        session = _make()
        session.transition_to(
            OcrSessionStatus.FAILED, NOW, error_code="OCR_ENGINE_UNAVAILABLE", error_message="boom"
        )
        assert session.error_code == "OCR_ENGINE_UNAVAILABLE"
        assert session.error_message == "boom"
