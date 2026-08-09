"""Tests for VietnamesePhone (§8.3.2)."""
import pytest
from hypothesis import given
from hypothesis import strategies as st

from cocas.domain.exceptions import ValidationError
from cocas.domain.value_objects.vietnamese_phone import VietnamesePhone

_VALID_MOBILE_PREFIXES = [
    "032", "086", "081", "088", "070", "089", "052", "092", "059", "099", "087",
]


class TestValid:
    @pytest.mark.parametrize("prefix", _VALID_MOBILE_PREFIXES)
    def test_accepts_known_prefixes(self, prefix: str) -> None:
        number = f"{prefix}1234567"
        assert VietnamesePhone(number).value == number

    def test_from_raw_strips_punctuation(self) -> None:
        assert VietnamesePhone.from_raw("091.234.5678").value == "0912345678"

    def test_from_raw_strips_spaces_and_parens(self) -> None:
        assert VietnamesePhone.from_raw("(091) 234 5678").value == "0912345678"

    def test_from_raw_normalizes_country_code_plus(self) -> None:
        assert VietnamesePhone.from_raw("+84912345678").value == "0912345678"

    def test_from_raw_normalizes_country_code_bare(self) -> None:
        assert VietnamesePhone.from_raw("84912345678").value == "0912345678"


class TestInvalid:
    @pytest.mark.parametrize(
        "raw",
        [
            "912345678",  # missing leading 0
            "09123456789",  # too long
            "0112345678",  # invalid prefix (01x not mobile)
            "091234567",  # too short
            "",
        ],
    )
    def test_rejects(self, raw: str) -> None:
        with pytest.raises(ValidationError):
            VietnamesePhone.from_raw(raw)


class TestCarrier:
    def test_known_carrier(self) -> None:
        assert VietnamesePhone("0321234567").carrier == "Viettel"

    def test_unknown_prefix_but_valid_format(self) -> None:
        # 0929xxxxxxx matches the mobile regex (9[0-9]) but is not in any table.
        phone = VietnamesePhone("0999234567")
        assert phone.carrier == "Gmobile"


@given(st.sampled_from(_VALID_MOBILE_PREFIXES), st.text(alphabet="0123456789", min_size=7, max_size=7))
def test_property_normalized_always_10_digits_starting_with_zero(prefix: str, rest: str) -> None:
    """Property #3 (§8.11): normalization always yields exactly 10 digits starting with 0."""
    phone = VietnamesePhone.from_raw(f"+84{prefix[1:]}{rest}")
    assert len(phone.value) == 10
    assert phone.value.startswith("0")
