"""§9.7 formatting table — one class per kind, plus the `None` golden rule."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from cocas.domain.services.value_formatter import (
    format_boolean,
    format_currency,
    format_currency_text,
    format_date,
    format_date_text,
    format_decimal,
    format_number,
    format_percent,
    format_value,
)


class TestDates:
    def test_date_is_zero_padded_day_month_year(self) -> None:
        assert format_date(date(2026, 8, 8)) == "08/08/2026"

    def test_date_text_spells_the_vietnamese_form(self) -> None:
        assert format_date_text(date(2026, 8, 8)) == "ngày 08 tháng 08 năm 2026"

    def test_single_digit_components_keep_two_digits(self) -> None:
        assert format_date(date(1990, 5, 14)) == "14/05/1990"


class TestNumbers:
    @pytest.mark.parametrize(
        ("amount", "expected"),
        [(0, "0"), (1500000, "1.500.000"), (999, "999"), (1000, "1.000"), (-2500, "-2.500")],
    )
    def test_currency_groups_with_dots(self, amount: int, expected: str) -> None:
        assert format_currency(amount) == expected

    def test_number_is_not_grouped(self) -> None:
        """⚠️ `2.000 bản` reads as a decimal in Vietnamese — grouping is
        `currency`'s job, not `number`'s."""
        assert format_number(2000) == "2000"

    def test_decimal_uses_a_comma(self) -> None:
        assert format_decimal(12.5) == "12,50"
        assert format_decimal(Decimal("0.05")) == "0,05"

    def test_percent_drops_a_pointless_fraction(self) -> None:
        assert format_percent(50) == "50%"
        assert format_percent(12.5) == "12,50%"


class TestBoolean:
    def test_true_and_false(self) -> None:
        assert format_boolean(True) == "Có"
        assert format_boolean(False) == "Không"

    def test_none_is_khong_not_empty(self) -> None:
        """⭐ The one exception to the empty-string rule (§9.7): a boolean
        field left blank means "no", and a blank cell in a contract where a
        Có/Không is expected reads as an unanswered question."""
        assert format_value(None, "boolean") == "Không"


class TestCurrencyText:
    @pytest.mark.parametrize(
        ("amount", "expected"),
        [
            (0, "Không đồng"),
            (1, "Một đồng"),
            (15, "Mười lăm đồng"),
            (21, "Hai mươi mốt đồng"),
            (24, "Hai mươi tư đồng"),
            (105, "Một trăm linh năm đồng"),
            (1000, "Một nghìn đồng"),
            (1500000, "Một triệu năm trăm nghìn đồng"),
            (1000005, "Một triệu không trăm linh năm đồng"),
            (2000000000, "Hai tỷ đồng"),
        ],
    )
    def test_vietnamese_number_words(self, amount: int, expected: str) -> None:
        assert format_currency_text(amount) == expected

    def test_negative_amount_is_prefixed(self) -> None:
        assert format_currency_text(-1000) == "Âm một nghìn đồng"


class TestGoldenRule:
    """⭐ §9.7 — `None` never renders as `"None"`. Every kind, every time."""

    @pytest.mark.parametrize(
        "kind",
        ["text", "date", "date_text", "number", "decimal", "currency",
         "currency_text", "percent", "enum", "securities_account"],
    )
    def test_none_renders_empty_for_every_kind(self, kind: str) -> None:
        assert format_value(None, kind) == ""

    def test_blank_string_collapses_to_empty(self) -> None:
        assert format_value("   ", "text") == ""

    def test_text_is_trimmed(self) -> None:
        assert format_value("  NGUYỄN VĂN AN  ", "text") == "NGUYỄN VĂN AN"

    def test_unknown_kind_falls_back_to_text_instead_of_raising(self) -> None:
        """⚠️ Kinds come from a template's `contract_fields` declaration; a
        typo there must not abort a contract for a waiting customer (P-08)."""
        assert format_value("008C123456", "no_such_kind") == "008C123456"

    def test_wrong_python_type_for_a_kind_falls_back_rather_than_crashing(self) -> None:
        assert format_value("hôm nay", "date") == "hôm nay"
