"""Tests for CitizenId (§8.3.1)."""
import pytest
from hypothesis import given
from hypothesis import strategies as st

from cocas.domain.exceptions import ValidationError
from cocas.domain.value_objects.citizen_id import CitizenId


class TestValid:
    def test_accepts_12_digits(self) -> None:
        assert CitizenId("001234567890").value == "001234567890"

    def test_accepts_all_zeros(self) -> None:
        assert CitizenId("000000000000").value == "000000000000"

    def test_from_raw_strips_separators(self) -> None:
        assert CitizenId.from_raw("001 234 567 890").value == "001234567890"

    def test_from_ocr_text_fixes_common_misreads(self) -> None:
        # O->0, I->1, S->5, B->8, Z->2, G->6, D->0
        assert CitizenId.from_ocr_text("OO1I34S6B890").value == "001134568890"


class TestInvalid:
    @pytest.mark.parametrize(
        "raw",
        [
            "00123456789",  # 11 digits — too short
            "0012345678901",  # 13 digits — too long
            "ABC234567890",  # letters
            "",  # empty
        ],
    )
    def test_rejects(self, raw: str) -> None:
        with pytest.raises(ValidationError) as exc_info:
            CitizenId(raw)
        assert exc_info.value.code == "INVALID_CITIZEN_ID_LENGTH"


class TestStructure:
    def test_province_code(self) -> None:
        assert CitizenId("001199012345").province_code == "001"

    def test_gender_century_digit_male_20th_century(self) -> None:
        cid = CitizenId("001099012345")
        assert cid.gender_century_digit == "0"
        assert cid.inferred_gender == "MALE"
        assert cid.inferred_birth_year_range == (1900, 1999)

    def test_gender_century_digit_female_21st_century(self) -> None:
        cid = CitizenId("001399012345")
        assert cid.gender_century_digit == "3"
        assert cid.inferred_gender == "FEMALE"
        assert cid.inferred_birth_year_range == (2000, 2099)

    def test_birth_year_suffix(self) -> None:
        assert CitizenId("001199012345").birth_year_suffix == "99"

    def test_immutable(self) -> None:
        cid = CitizenId("001234567890")
        with pytest.raises(AttributeError):
            cid.value = "999999999999"  # type: ignore[misc]


@given(st.text(alphabet="0123456789", min_size=0, max_size=25))
def test_property_accepts_all_12_digit_strings_rejects_others(raw: str) -> None:
    """Property #2 (§8.11): accepts every 12-digit string, rejects every other."""
    if len(raw) == 12:
        assert CitizenId(raw).value == raw
    else:
        with pytest.raises(ValidationError):
            CitizenId(raw)
