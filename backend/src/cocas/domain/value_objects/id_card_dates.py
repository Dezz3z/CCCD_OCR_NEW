"""IdCardDates value object — issue/expiry pair for a CCCD (§8.3.8, V-OCR-005..015)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from cocas.domain.exceptions import ValidationError

MIN_AGE_AT_ISSUE = 14
NO_EXPIRY_AGE_THRESHOLD = 60
EXPIRY_SOON_DAYS = 90

# ⭐ What a card without an expiry prints where the date would be. Lives in
# Domain because both the extractor (Infrastructure) and the normalizer
# (Domain) have to agree on the exact string — a "no expiry" spelled two ways
# is two different values to fusion's consensus rule.
NO_EXPIRY_TEXT = "KHÔNG THỜI HẠN"


@dataclass(frozen=True, slots=True)
class IdCardDates:
    """The issue date and (optional) expiry date of a CCCD.

    `expiry_date is None` represents "KHÔNG THỜI HẠN" (no expiry) — this is
    a valid, first-class state, not a missing value.
    """

    issue_date: date
    expiry_date: date | None

    def __post_init__(self) -> None:
        if self.expiry_date is not None and self.issue_date > self.expiry_date:
            raise ValidationError(
                "Ngày cấp phải trước hoặc bằng ngày hết hạn.",
                code="ISSUE_AFTER_EXPIRY",
                field="expiry_date",
            )

    @property
    def is_no_expiry(self) -> bool:
        return self.expiry_date is None

    def is_expired(self, today: date) -> bool:
        """False for a no-expiry card."""
        return self.expiry_date is not None and self.expiry_date < today

    def is_expiring_soon(self, today: date, within_days: int = EXPIRY_SOON_DAYS) -> bool:
        if self.expiry_date is None:
            return False
        return 0 <= (self.expiry_date - today).days < within_days

    def age_at_issue(self, date_of_birth: date) -> int:
        """Age in whole years on the issue date."""
        return _age_in_years(date_of_birth, self.issue_date)

    def current_age(self, date_of_birth: date, today: date) -> int:
        return _age_in_years(date_of_birth, today)

    def should_have_no_expiry(self, date_of_birth: date) -> bool:
        """🔵 True when the citizen was ≥60 at issue — such cards are usually lifelong."""
        return self.age_at_issue(date_of_birth) >= NO_EXPIRY_AGE_THRESHOLD


def _age_in_years(born: date, on: date) -> int:
    years = on.year - born.year
    if (on.month, on.day) < (born.month, born.day):
        years -= 1
    return years
