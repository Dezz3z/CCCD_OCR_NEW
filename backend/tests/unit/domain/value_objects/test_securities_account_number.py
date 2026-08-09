"""Tests for SecuritiesAccountNumber (§8.3.5)."""
import pytest
from hypothesis import given
from hypothesis import strategies as st

from cocas.domain.exceptions import ValidationError
from cocas.domain.value_objects.securities_account_number import SecuritiesAccountNumber


class TestValid:
    def test_full_form(self) -> None:
        assert SecuritiesAccountNumber("008C123456").value == "008C123456"

    def test_all_zeros_customer_part(self) -> None:
        SecuritiesAccountNumber("008C000000")

    def test_from_raw_auto_prefixes_bare_6_digits(self) -> None:
        assert SecuritiesAccountNumber.from_raw("123456").value == "008C123456"

    def test_from_raw_strips_spaces_and_dashes(self) -> None:
        assert SecuritiesAccountNumber.from_raw("008C 123-456").value == "008C123456"

    def test_from_raw_uppercases(self) -> None:
        assert SecuritiesAccountNumber.from_raw("008c123456").value == "008C123456"

    def test_display_grouping(self) -> None:
        assert SecuritiesAccountNumber("008C123456").display == "008C 123456"


class TestInvalid:
    def test_missing_digit(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            SecuritiesAccountNumber("008C12345")
        assert exc_info.value.code == "INVALID_SECURITIES_ACCOUNT"

    def test_wrong_member_code_strict(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            SecuritiesAccountNumber.from_raw("009C123456", strict=True)
        assert exc_info.value.code == "INVALID_MEMBER_CODE"

    def test_wrong_member_code_non_strict_allowed(self) -> None:
        vo = SecuritiesAccountNumber.from_raw("009C123456", strict=False)
        assert vo.member_code == "009"

    def test_malformed(self) -> None:
        with pytest.raises(ValidationError):
            SecuritiesAccountNumber("NOTVALID")

    def test_empty(self) -> None:
        with pytest.raises(ValidationError):
            SecuritiesAccountNumber("")


@given(st.text(alphabet="0123456789 -", min_size=1, max_size=15))
def test_property_from_raw_always_valid_pattern_or_raises(raw: str) -> None:
    """Property #4 (§8.11): from_raw always yields ^\\d{3}C\\d{6}$ or raises."""
    try:
        vo = SecuritiesAccountNumber.from_raw(raw, strict=False)
    except ValidationError:
        return
    assert len(vo.value) == 10
    assert vo.value[3] == "C"
    assert vo.value[0:3].isdigit()
    assert vo.value[4:10].isdigit()
