"""Tests for EmailAddress (§8.3.3)."""
import pytest

from cocas.domain.exceptions import ValidationError
from cocas.domain.value_objects.email_address import EmailAddress


class TestValid:
    def test_standard_email(self) -> None:
        assert EmailAddress("user@example.com").value == "user@example.com"

    def test_dots_and_plus_tag(self) -> None:
        EmailAddress("user.name+tag@example.co.uk")

    def test_from_raw_trims_and_lowercases(self) -> None:
        assert EmailAddress.from_raw("  User@EXAMPLE.com  ").value == "user@example.com"

    def test_local_part_exactly_64_chars(self) -> None:
        local = "a" * 64
        EmailAddress(f"{local}@example.com")

    def test_total_exactly_254_chars(self) -> None:
        # 254 total: local(63) + '@' + domain padded to hit exactly 254.
        domain_len = 254 - 63 - 1
        domain = "b" * (domain_len - 4) + ".com"
        email = f"{'a' * 63}@{domain}"
        assert len(email) == 254
        EmailAddress(email)


class TestInvalid:
    def test_missing_domain(self) -> None:
        with pytest.raises(ValidationError):
            EmailAddress("invalid.email@")

    def test_missing_local_part(self) -> None:
        with pytest.raises(ValidationError):
            EmailAddress("@example.com")

    def test_consecutive_dots(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            EmailAddress("a..b@c.com")
        assert exc_info.value.code == "INVALID_EMAIL"

    def test_local_part_65_chars_too_long(self) -> None:
        local = "a" * 65
        with pytest.raises(ValidationError) as exc_info:
            EmailAddress(f"{local}@example.com")
        assert exc_info.value.code == "INVALID_EMAIL_LENGTH"

    def test_total_255_chars_too_long(self) -> None:
        domain_len = 255 - 63 - 1
        domain = "b" * (domain_len - 4) + ".com"
        email = f"{'a' * 63}@{domain}"
        assert len(email) == 255
        with pytest.raises(ValidationError) as exc_info:
            EmailAddress(email)
        assert exc_info.value.code == "INVALID_EMAIL_LENGTH"

    def test_empty_string(self) -> None:
        with pytest.raises(ValidationError):
            EmailAddress("")


class TestTypoSuggestion:
    def test_known_typo_domain(self) -> None:
        assert EmailAddress("user@gmai.com").typo_suggestion == "user@gmail.com"

    def test_no_suggestion_for_correct_domain(self) -> None:
        assert EmailAddress("user@gmail.com").typo_suggestion is None
