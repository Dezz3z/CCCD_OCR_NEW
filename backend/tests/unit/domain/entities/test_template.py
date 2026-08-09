"""Tests for Template entity (§4.4.8)."""
import uuid
from datetime import UTC, datetime

import pytest

from cocas.domain.entities.template import Template
from cocas.domain.exceptions import BusinessRuleViolation

NOW = datetime(2026, 8, 9, tzinfo=UTC)


def _make(**overrides: object) -> Template:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "code": "01A_HD_GDN",
        "name": "Mẫu số 01A/HĐ-GĐN",
        "party_schema": [{"key": "holder", "entity_type": "INDIVIDUAL", "min": 1, "max": 1}],
        "contract_no_pattern": "01A-GDN-{yyyy}{MM}-{seq:05d}",
        "export_name_pattern": "Mẫu 01A - {full_name}",
        "created_at": NOW,
    }
    defaults.update(overrides)
    return Template(**defaults)  # type: ignore[arg-type]


class TestSequence:
    def test_starts_at_zero(self) -> None:
        assert _make().contract_no_seq == 0

    def test_increment_returns_next_value(self) -> None:
        template = _make()
        assert template.next_contract_sequence() == 1
        assert template.next_contract_sequence() == 2
        assert template.contract_no_seq == 2


class TestLifecycle:
    def test_activate_version(self) -> None:
        template = _make()
        version_id = uuid.uuid4()
        template.activate_version(version_id, NOW)
        assert template.active_version_id == version_id
        assert template.updated_at == NOW

    def test_deactivate(self) -> None:
        template = _make()
        template.deactivate(NOW)
        assert template.is_active is False

    def test_soft_delete(self) -> None:
        template = _make()
        template.soft_delete(NOW)
        assert template.is_deleted is True
        assert template.is_active is False

    def test_double_soft_delete_rejected(self) -> None:
        template = _make()
        template.soft_delete(NOW)
        with pytest.raises(BusinessRuleViolation) as exc_info:
            template.soft_delete(NOW)
        assert exc_info.value.code == "ALREADY_DELETED"
