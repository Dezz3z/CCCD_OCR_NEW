"""Customer entity (§4.4.6 `customer`).

⭐ Holds decrypted, plain business values — the `_enc`/`_bidx`/`_masked`
column split in the CSDL is a persistence concern handled entirely by the
repository/mapper (§12.14: "Giải mã PII xảy ra TRONG repository — tầng trên
không biết dữ liệu từng được mã hoá").
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from cocas.domain.enums.data_quality import DataQuality
from cocas.domain.enums.gender import Gender
from cocas.domain.exceptions import BusinessRuleViolation
from cocas.domain.value_objects.citizen_id import CitizenId
from cocas.domain.value_objects.email_address import EmailAddress
from cocas.domain.value_objects.id_card_dates import IdCardDates
from cocas.domain.value_objects.issue_place import IssuePlace
from cocas.domain.value_objects.person_name import PersonName
from cocas.domain.value_objects.securities_account_number import SecuritiesAccountNumber
from cocas.domain.value_objects.vietnamese_phone import VietnamesePhone


@dataclass(slots=True)
class Customer:
    """A person whose CCCD has been captured (by OCR and/or manual entry)."""

    id: uuid.UUID
    created_by: str
    full_name: PersonName
    id_number: CitizenId
    date_of_birth: date
    issue_place: IssuePlace
    id_card_dates: IdCardDates
    phone: VietnamesePhone
    email: EmailAddress
    address: str
    data_quality: DataQuality
    created_at: datetime
    ocr_session_id: uuid.UUID | None = None
    gender: Gender | None = None
    securities_account_no: SecuritiesAccountNumber | None = None
    securities_account_opened_at: date | None = None
    province_code: str | None = None
    note: str | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.date_of_birth >= self.id_card_dates.issue_date:
            raise BusinessRuleViolation(
                "Ngày sinh phải trước ngày cấp.", code="DOB_AFTER_ISSUE_DATE"
            )
        if len(self.address) < 10:
            raise BusinessRuleViolation(
                "Địa chỉ phải có ít nhất 10 ký tự.", code="INVALID_ADDRESS_LENGTH", field="address"
            )

    @property
    def birth_year(self) -> int:
        return self.date_of_birth.year

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def update_contact(
        self, phone: VietnamesePhone, email: EmailAddress, address: str, now: datetime
    ) -> None:
        if len(address) < 10:
            raise BusinessRuleViolation(
                "Địa chỉ phải có ít nhất 10 ký tự.", code="INVALID_ADDRESS_LENGTH", field="address"
            )
        self.phone = phone
        self.email = email
        self.address = address
        self.updated_at = now

    def soft_delete(self, now: datetime) -> None:
        if self.is_deleted:
            raise BusinessRuleViolation("Khách hàng đã bị xoá trước đó.", code="ALREADY_DELETED")
        self.deleted_at = now
        self.updated_at = now
