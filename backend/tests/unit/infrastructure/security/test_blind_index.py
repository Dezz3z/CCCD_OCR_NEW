"""Tests for blind-index normalization (§4.8.4)."""
from __future__ import annotations

import pytest

from cocas.domain.ports.crypto import BidxField
from cocas.infrastructure.security.blind_index import normalize_for_blind_index


class TestIdNumber:
    def test_strips_separators(self) -> None:
        assert normalize_for_blind_index("001 199 012 345", BidxField.ID_NUMBER) == "001199012345"


class TestPhone:
    def test_normalizes_country_code(self) -> None:
        assert normalize_for_blind_index("+84912345678", BidxField.PHONE) == "0912345678"

    def test_already_normalized_unchanged(self) -> None:
        assert normalize_for_blind_index("0912345678", BidxField.PHONE) == "0912345678"


class TestEmail:
    def test_lowercases_and_trims(self) -> None:
        assert normalize_for_blind_index("  User@EXAMPLE.com  ", BidxField.EMAIL) == "user@example.com"


class TestBankAccountNumber:
    def test_strips_non_digits(self) -> None:
        assert normalize_for_blind_index("0123-4567-89", BidxField.BANK_ACCOUNT_NUMBER) == "0123456789"


class TestSecuritiesAccount:
    def test_uppercases_and_strips_spaces(self) -> None:
        assert (
            normalize_for_blind_index("008c 123456", BidxField.SECURITIES_ACCOUNT) == "008C123456"
        )

    def test_bare_6_digits_gets_prefixed(self) -> None:
        assert normalize_for_blind_index("123456", BidxField.SECURITIES_ACCOUNT) == "008C123456"


class TestConsistencyWithVO:
    """The whole point of reusing the VOs: same input, same normalized output."""

    @pytest.mark.parametrize(
        ("field", "raw", "expected"),
        [
            (BidxField.ID_NUMBER, "001-199-012-345", "001199012345"),
            (BidxField.PHONE, "84 91 234 5678", "0912345678"),
            (BidxField.EMAIL, "A@B.COM", "a@b.com"),
        ],
    )
    def test_matches_vo_normalization(self, field: BidxField, raw: str, expected: str) -> None:
        assert normalize_for_blind_index(raw, field) == expected
