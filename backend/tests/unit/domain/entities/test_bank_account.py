"""Tests for BankAccount entity (§4.4.7)."""
import uuid
from datetime import UTC, datetime

import pytest

from cocas.domain.entities.bank_account import BankAccount
from cocas.domain.exceptions import BusinessRuleViolation
from cocas.domain.value_objects.bank_account_number import BankAccountNumber

NOW = datetime(2026, 8, 9, tzinfo=UTC)


def _make(**overrides: object) -> BankAccount:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "customer_id": uuid.uuid4(),
        "account_number": BankAccountNumber("0123456789013"),
        "bank_name": "Vietcombank",
        "branch": "Chi nhánh Hà Nội",
        "created_at": NOW,
    }
    defaults.update(overrides)
    return BankAccount(**defaults)  # type: ignore[arg-type]


class TestConstruction:
    def test_valid(self) -> None:
        account = _make()
        assert account.is_primary is True
        assert account.is_deleted is False


class TestSoftDelete:
    def test_soft_delete(self) -> None:
        account = _make()
        account.soft_delete(NOW)
        assert account.is_deleted is True
        assert account.updated_at == NOW

    def test_double_soft_delete_rejected(self) -> None:
        account = _make()
        account.soft_delete(NOW)
        with pytest.raises(BusinessRuleViolation) as exc_info:
            account.soft_delete(NOW)
        assert exc_info.value.code == "ALREADY_DELETED"
