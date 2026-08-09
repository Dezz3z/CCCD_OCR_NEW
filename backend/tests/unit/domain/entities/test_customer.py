"""Tests for Customer entity (§4.4.6)."""
import uuid
from datetime import UTC, date, datetime

import pytest

from cocas.domain.entities.customer import Customer
from cocas.domain.enums.data_quality import DataQuality
from cocas.domain.exceptions import BusinessRuleViolation
from cocas.domain.value_objects.citizen_id import CitizenId
from cocas.domain.value_objects.email_address import EmailAddress
from cocas.domain.value_objects.id_card_dates import IdCardDates
from cocas.domain.value_objects.issue_place import BO_CONG_AN, IssuePlace
from cocas.domain.value_objects.person_name import PersonName
from cocas.domain.value_objects.vietnamese_phone import VietnamesePhone

NOW = datetime(2026, 8, 9, tzinfo=UTC)


def _make(**overrides: object) -> Customer:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "created_by": "phthang",
        "full_name": PersonName("NGUYỄN VĂN AN"),
        "id_number": CitizenId("001199012345"),
        "date_of_birth": date(1990, 5, 14),
        "issue_place": IssuePlace(BO_CONG_AN),
        "id_card_dates": IdCardDates(date(2021, 5, 14), date(2031, 5, 14)),
        "phone": VietnamesePhone("0912345678"),
        "email": EmailAddress("an@example.com"),
        "address": "123 Đường Láng, Đống Đa, Hà Nội",
        "data_quality": DataQuality.OCR_VERIFIED,
        "created_at": NOW,
    }
    defaults.update(overrides)
    return Customer(**defaults)  # type: ignore[arg-type]


class TestConstruction:
    def test_valid_customer(self) -> None:
        customer = _make()
        assert customer.birth_year == 1990
        assert customer.is_deleted is False

    def test_dob_after_issue_date_rejected(self) -> None:
        with pytest.raises(BusinessRuleViolation) as exc_info:
            _make(
                date_of_birth=date(2022, 1, 1),
                id_card_dates=IdCardDates(date(2021, 5, 14), date(2031, 5, 14)),
            )
        assert exc_info.value.code == "DOB_AFTER_ISSUE_DATE"

    def test_address_too_short_rejected(self) -> None:
        with pytest.raises(BusinessRuleViolation) as exc_info:
            _make(address="short")
        assert exc_info.value.code == "INVALID_ADDRESS_LENGTH"


class TestUpdateContact:
    def test_updates_fields(self) -> None:
        customer = _make()
        new_phone = VietnamesePhone("0987654321")
        new_email = EmailAddress("new@example.com")
        customer.update_contact(new_phone, new_email, "456 Đường mới, Hà Nội", NOW)
        assert customer.phone == new_phone
        assert customer.email == new_email
        assert customer.address == "456 Đường mới, Hà Nội"
        assert customer.updated_at == NOW

    def test_address_too_short_rejected(self) -> None:
        customer = _make()
        with pytest.raises(BusinessRuleViolation):
            customer.update_contact(customer.phone, customer.email, "short", NOW)


class TestSoftDelete:
    def test_soft_delete(self) -> None:
        customer = _make()
        customer.soft_delete(NOW)
        assert customer.is_deleted is True

    def test_double_soft_delete_rejected(self) -> None:
        customer = _make()
        customer.soft_delete(NOW)
        with pytest.raises(BusinessRuleViolation) as exc_info:
            customer.soft_delete(NOW)
        assert exc_info.value.code == "ALREADY_DELETED"
