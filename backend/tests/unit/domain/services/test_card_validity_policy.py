"""Tests for CardValidityPolicy (V-OCR-013/014/015)."""
from datetime import date

from cocas.domain.services.card_validity_policy import CardValidityPolicy, CardValidityStatus
from cocas.domain.value_objects.id_card_dates import IdCardDates

POLICY = CardValidityPolicy()


class TestValid:
    def test_far_from_expiry(self) -> None:
        dates = IdCardDates(date(2020, 1, 1), date(2030, 1, 1))
        report = POLICY.evaluate(dates, date(1990, 5, 14), date(2024, 1, 1))
        assert report.status == CardValidityStatus.CARD_VALID
        assert "còn hiệu lực" in report.message_vi

    def test_message_contains_formatted_expiry(self) -> None:
        dates = IdCardDates(date(2020, 5, 14), date(2030, 5, 14))
        report = POLICY.evaluate(dates, date(1990, 5, 14), date(2026, 8, 9))
        assert "14/05/2030" in report.message_vi


class TestNoExpiry:
    def test_no_expiry_status(self) -> None:
        dates = IdCardDates(date(2020, 1, 1), None)
        report = POLICY.evaluate(dates, date(1950, 1, 1), date(2024, 1, 1))
        assert report.status == CardValidityStatus.CARD_NO_EXPIRY

    def test_no_expiry_hint_true_for_60_plus(self) -> None:
        dates = IdCardDates(date(2020, 1, 1), None)
        report = POLICY.evaluate(dates, date(1950, 1, 1), date(2024, 1, 1))
        assert report.should_have_no_expiry_hint is True


class TestExpired:
    def test_expired_status(self) -> None:
        dates = IdCardDates(date(2010, 1, 1), date(2020, 1, 1))
        report = POLICY.evaluate(dates, date(1990, 5, 14), date(2024, 1, 1))
        assert report.status == CardValidityStatus.CARD_EXPIRED
        assert "hết hạn ngày" in report.message_vi

    def test_expiry_boundary_today_is_not_expired(self) -> None:
        dates = IdCardDates(date(2010, 1, 1), date(2024, 1, 1))
        report = POLICY.evaluate(dates, date(1990, 5, 14), date(2024, 1, 1))
        assert report.status != CardValidityStatus.CARD_EXPIRED


class TestExpiringSoon:
    def test_within_90_days(self) -> None:
        dates = IdCardDates(date(2020, 1, 1), date(2024, 3, 1))
        report = POLICY.evaluate(dates, date(1990, 5, 14), date(2024, 1, 1))
        assert report.status == CardValidityStatus.CARD_EXPIRING_SOON
        assert "sẽ hết hạn sau" in report.message_vi

    def test_just_outside_90_days_is_valid(self) -> None:
        dates = IdCardDates(date(2020, 1, 1), date(2024, 4, 15))
        report = POLICY.evaluate(dates, date(1990, 5, 14), date(2024, 1, 1))
        assert report.status == CardValidityStatus.CARD_VALID


class TestNoExpiryHint:
    def test_hint_false_when_young_at_issue(self) -> None:
        dates = IdCardDates(date(2021, 5, 14), date(2031, 5, 14))
        report = POLICY.evaluate(dates, date(1990, 5, 14), date(2024, 1, 1))
        assert report.should_have_no_expiry_hint is False

    def test_hint_true_when_60_at_issue_but_has_expiry(self) -> None:
        """A card WITH an expiry date, issued to someone ≥60 — hint should still fire."""
        dates = IdCardDates(date(2021, 5, 14), date(2031, 5, 14))
        report = POLICY.evaluate(dates, date(1961, 5, 14), date(2024, 1, 1))
        assert report.should_have_no_expiry_hint is True
