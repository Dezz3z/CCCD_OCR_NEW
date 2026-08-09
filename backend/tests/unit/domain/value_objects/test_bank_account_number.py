"""Tests for BankAccountNumber (§8.3.4)."""
import pytest

from cocas.domain.exceptions import ValidationError
from cocas.domain.value_objects.bank_account_number import BankAccountNumber


class TestValid:
    def test_10_digit_account(self) -> None:
        assert BankAccountNumber("0123456789").value == "0123456789"

    def test_13_digit_account(self) -> None:
        BankAccountNumber("1234567890123")

    def test_minimum_6_digits(self) -> None:
        BankAccountNumber("123456")

    def test_maximum_20_digits(self) -> None:
        BankAccountNumber("1" * 20)

    def test_from_raw_strips_non_digits(self) -> None:
        assert BankAccountNumber.from_raw("0123-4567-89").value == "0123456789"


class TestInvalid:
    def test_5_digits_below_minimum(self) -> None:
        with pytest.raises(ValidationError):
            BankAccountNumber("12345")

    def test_21_digits_above_maximum(self) -> None:
        with pytest.raises(ValidationError):
            BankAccountNumber("1" * 21)

    def test_contains_letters(self) -> None:
        with pytest.raises(ValidationError):
            BankAccountNumber("ABC3456789")

    def test_empty(self) -> None:
        with pytest.raises(ValidationError):
            BankAccountNumber("")


class TestBankLengthMatch:
    def test_matches_bank_range(self) -> None:
        assert BankAccountNumber("0123456789123").matches_bank_length(13, 13)

    def test_does_not_match_bank_range(self) -> None:
        assert not BankAccountNumber("012345678912").matches_bank_length(13, 13)
