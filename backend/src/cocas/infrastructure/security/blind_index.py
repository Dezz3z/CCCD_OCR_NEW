"""Blind-index normalization (§4.8.4).

Each `BidxField` normalizes its raw value the same way its Domain Value
Object does, before hashing — reusing the VO's own `from_raw()` keeps this
normalization defined in exactly one place instead of drifting from the
validation rules over time.
"""
from __future__ import annotations

from cocas.domain.ports.crypto import BidxField
from cocas.domain.value_objects.bank_account_number import BankAccountNumber
from cocas.domain.value_objects.citizen_id import CitizenId
from cocas.domain.value_objects.email_address import EmailAddress
from cocas.domain.value_objects.securities_account_number import SecuritiesAccountNumber
from cocas.domain.value_objects.vietnamese_phone import VietnamesePhone


def normalize_for_blind_index(value: str, field: BidxField) -> str:
    """Apply the same normalization the field's VO would, per §4.8.4's table."""
    if field is BidxField.ID_NUMBER:
        return CitizenId.from_raw(value).value
    if field is BidxField.PHONE:
        return VietnamesePhone.from_raw(value).value
    if field is BidxField.EMAIL:
        return EmailAddress.from_raw(value).value
    if field is BidxField.BANK_ACCOUNT_NUMBER:
        return BankAccountNumber.from_raw(value).value
    if field is BidxField.SECURITIES_ACCOUNT:
        return SecuritiesAccountNumber.from_raw(value, strict=False).value
    raise AssertionError(f"Unhandled BidxField: {field!r}")  # pragma: no cover
