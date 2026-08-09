"""CardValidityPolicy — packages V-OCR-013/014/015 into one reusable report (§07 D5, §08 V-OCR-*).

`IdCardDates` (the Value Object) already carries the raw predicates
(`is_expired`, `is_expiring_soon`, `should_have_no_expiry`) — this service
just turns them into the one status + Vietnamese message the API/Dashboard
render, per the sample response in docs/design/05-thiet-ke-api.md:
`"Thẻ còn hiệu lực đến 14/05/2030 (còn 3 năm 9 tháng)."`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from cocas.domain.value_objects.id_card_dates import IdCardDates


class CardValidityStatus(str, Enum):
    CARD_VALID = "CARD_VALID"
    CARD_NO_EXPIRY = "CARD_NO_EXPIRY"
    CARD_EXPIRING_SOON = "CARD_EXPIRING_SOON"
    CARD_EXPIRED = "CARD_EXPIRED"


@dataclass(frozen=True, slots=True)
class CardValidityReport:
    status: CardValidityStatus
    message_vi: str
    should_have_no_expiry_hint: bool


class CardValidityPolicy:
    """Domain Service — evaluate a CCCD's current validity."""

    def evaluate(
        self, dates: IdCardDates, date_of_birth: date, today: date
    ) -> CardValidityReport:
        hint = dates.should_have_no_expiry(date_of_birth)

        if dates.is_no_expiry:
            return CardValidityReport(
                status=CardValidityStatus.CARD_NO_EXPIRY,
                message_vi="Thẻ có giá trị không thời hạn.",
                should_have_no_expiry_hint=hint,
            )

        if dates.is_expired(today):
            assert dates.expiry_date is not None
            return CardValidityReport(
                status=CardValidityStatus.CARD_EXPIRED,
                message_vi=f"CCCD đã hết hạn ngày {_format_date(dates.expiry_date)}.",
                should_have_no_expiry_hint=hint,
            )

        if dates.is_expiring_soon(today):
            assert dates.expiry_date is not None
            days_left = (dates.expiry_date - today).days
            return CardValidityReport(
                status=CardValidityStatus.CARD_EXPIRING_SOON,
                message_vi=f"CCCD sẽ hết hạn sau {days_left} ngày.",
                should_have_no_expiry_hint=hint,
            )

        assert dates.expiry_date is not None
        return CardValidityReport(
            status=CardValidityStatus.CARD_VALID,
            message_vi=(
                f"Thẻ còn hiệu lực đến {_format_date(dates.expiry_date)} "
                f"({_format_remaining(today, dates.expiry_date)})."
            ),
            should_have_no_expiry_hint=hint,
        )


def _format_date(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _format_remaining(today: date, expiry: date) -> str:
    total_months = (expiry.year - today.year) * 12 + (expiry.month - today.month)
    if expiry.day < today.day:
        total_months -= 1
    years, months = divmod(max(total_months, 0), 12)
    parts = []
    if years:
        parts.append(f"{years} năm")
    if months or not years:
        parts.append(f"{months} tháng")
    return "còn " + " ".join(parts)
