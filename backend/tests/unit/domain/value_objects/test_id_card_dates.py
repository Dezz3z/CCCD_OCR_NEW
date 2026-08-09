"""Tests for IdCardDates (§8.3.8, V-OCR-005..015)."""
from datetime import date

import pytest

from cocas.domain.exceptions import ValidationError
from cocas.domain.value_objects.id_card_dates import IdCardDates


class TestValid:
    def test_issue_before_expiry(self) -> None:
        IdCardDates(date(2023, 1, 1), date(2033, 1, 1))

    def test_issue_equal_to_expiry_boundary(self) -> None:
        IdCardDates(date(2023, 1, 1), date(2023, 1, 1))

    def test_no_expiry(self) -> None:
        dates = IdCardDates(date(2023, 1, 1), None)
        assert dates.is_no_expiry is True


class TestInvalid:
    def test_expiry_before_issue(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            IdCardDates(date(2025, 1, 1), date(2020, 1, 1))
        assert exc_info.value.code == "ISSUE_AFTER_EXPIRY"


class TestBehavior:
    def test_is_expired_true(self) -> None:
        dates = IdCardDates(date(2010, 1, 1), date(2020, 1, 1))
        assert dates.is_expired(date(2024, 1, 1)) is True

    def test_is_expired_false_for_no_expiry(self) -> None:
        dates = IdCardDates(date(2010, 1, 1), None)
        assert dates.is_expired(date(2099, 1, 1)) is False

    def test_is_expiring_soon(self) -> None:
        dates = IdCardDates(date(2020, 1, 1), date(2024, 3, 1))
        assert dates.is_expiring_soon(date(2024, 1, 1), within_days=90) is True

    def test_not_expiring_soon_when_far_away(self) -> None:
        dates = IdCardDates(date(2020, 1, 1), date(2030, 1, 1))
        assert dates.is_expiring_soon(date(2024, 1, 1)) is False

    def test_age_at_issue(self) -> None:
        dates = IdCardDates(date(2021, 5, 14), date(2031, 5, 14))
        assert dates.age_at_issue(date(1990, 5, 14)) == 31

    def test_age_at_issue_before_birthday_in_year(self) -> None:
        dates = IdCardDates(date(2021, 5, 1), date(2031, 5, 1))
        assert dates.age_at_issue(date(1990, 5, 14)) == 30

    def test_should_have_no_expiry_when_60_at_issue(self) -> None:
        dates = IdCardDates(date(2021, 5, 14), date(2021, 5, 14))
        assert dates.should_have_no_expiry(date(1961, 5, 14)) is True

    def test_should_not_have_no_expiry_when_under_60(self) -> None:
        dates = IdCardDates(date(2021, 5, 14), date(2031, 5, 14))
        assert dates.should_have_no_expiry(date(1990, 5, 14)) is False
