"""Tests for CardImage entity (§4.4.1)."""
import uuid
from datetime import UTC, datetime

import pytest

from cocas.domain.entities.card_image import CardImage
from cocas.domain.enums.card_side import CardSide
from cocas.domain.exceptions import BusinessRuleViolation
from cocas.domain.value_objects.confidence_score import ConfidenceScore

NOW = datetime(2026, 8, 9, tzinfo=UTC)


def _make(**overrides: object) -> CardImage:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "uploaded_by": "phthang",
        "document_type_id": uuid.uuid4(),
        "side_hint": CardSide.FRONT,
        "vault_path": "card_image/2026/08/09/abc.enc",
        "mime_type": "image/jpeg",
        "width_px": 1600,
        "height_px": 1000,
        "size_bytes": 2_000_000,
        "sha256": b"\x00" * 32,
        "created_at": NOW,
    }
    defaults.update(overrides)
    return CardImage(**defaults)  # type: ignore[arg-type]


class TestConstruction:
    def test_valid_image(self) -> None:
        img = _make()
        assert img.is_purged is False

    def test_width_below_minimum(self) -> None:
        with pytest.raises(BusinessRuleViolation) as exc_info:
            _make(width_px=100)
        assert exc_info.value.code == "INVALID_IMAGE_WIDTH"

    def test_height_above_maximum(self) -> None:
        with pytest.raises(BusinessRuleViolation) as exc_info:
            _make(height_px=20000)
        assert exc_info.value.code == "INVALID_IMAGE_HEIGHT"

    def test_size_too_large(self) -> None:
        with pytest.raises(BusinessRuleViolation) as exc_info:
            _make(size_bytes=20_000_000)
        assert exc_info.value.code == "IMAGE_TOO_LARGE"

    def test_boundary_min_edge_allowed(self) -> None:
        _make(width_px=320, height_px=320)

    def test_boundary_max_size_allowed(self) -> None:
        _make(size_bytes=10 * 1024 * 1024)


class TestResolvedSide:
    def test_defaults_to_hint(self) -> None:
        img = _make(side_hint=CardSide.FRONT)
        assert img.resolved_side == CardSide.FRONT

    def test_resolve_side_overrides(self) -> None:
        img = _make(side_hint=CardSide.UNKNOWN)
        img.resolve_side(CardSide.BACK, ConfidenceScore(0.92))
        assert img.resolved_side == CardSide.BACK
        assert img.side_confidence is not None
        assert img.side_confidence.value == 0.92


class TestPurge:
    def test_purge_sets_fields(self) -> None:
        img = _make()
        img.purge("RETENTION_POLICY", NOW)
        assert img.is_purged is True
        assert img.purge_reason == "RETENTION_POLICY"
        assert img.purged_at == NOW

    def test_double_purge_rejected(self) -> None:
        img = _make()
        img.purge("USER_REQUEST", NOW)
        with pytest.raises(BusinessRuleViolation) as exc_info:
            img.purge("USER_REQUEST", NOW)
        assert exc_info.value.code == "ALREADY_PURGED"
