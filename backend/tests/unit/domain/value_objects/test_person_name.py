"""Tests for PersonName (§8.3.6)."""
import unicodedata

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cocas.domain.exceptions import ValidationError
from cocas.domain.value_objects.person_name import PersonName


class TestValid:
    def test_typical_name(self) -> None:
        assert PersonName("NGUYỄN VĂN AN").value == "NGUYỄN VĂN AN"

    def test_famous_name(self) -> None:
        PersonName("HỒ CHÍ MINH")

    def test_single_char_last_name(self) -> None:
        PersonName("TRẦN THỊ B")

    def test_from_raw_uppercases(self) -> None:
        assert PersonName.from_raw("nguyễn văn an").value == "NGUYỄN VĂN AN"

    def test_from_raw_collapses_whitespace(self) -> None:
        assert PersonName.from_raw("NGUYỄN   VĂN   AN").value == "NGUYỄN VĂN AN"

    def test_allows_hyphen_and_apostrophe(self) -> None:
        PersonName("NGUYỄN-VĂN O'BRIEN")

    def test_minimum_length_2(self) -> None:
        PersonName("AN")

    def test_maximum_length_100(self) -> None:
        PersonName("A" * 100)


class TestInvalid:
    def test_numbers_only(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            PersonName("123456")
        assert exc_info.value.code == "INVALID_CHARACTER"

    def test_single_character_too_short(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            PersonName("A")
        assert exc_info.value.code == "INVALID_NAME_LENGTH"

    def test_forbidden_symbol(self) -> None:
        with pytest.raises(ValidationError):
            PersonName("NGUYỄN×VĂN")  # noqa: RUF001 — intentional non-Vietnamese symbol

    def test_empty(self) -> None:
        with pytest.raises(ValidationError):
            PersonName("")

    def test_over_100_chars(self) -> None:
        with pytest.raises(ValidationError):
            PersonName("A" * 101)


class TestWordCount:
    def test_single_word_allowed_but_flagged(self) -> None:
        name = PersonName("AN")
        assert name.word_count == 1

    def test_two_words_no_flag(self) -> None:
        name = PersonName("TRẦN AN")
        assert name.word_count == 2


class TestOcrDigitFixup:
    def test_fixes_digit_between_letters(self) -> None:
        # "NGUYEN" with a 1 misread as I between letters -> corrected to letter.
        assert PersonName.from_ocr_text("NGUY1N VAN AN").value == "NGUYIN VAN AN"

    def test_does_not_fix_standalone_digit(self) -> None:
        # A digit at a word boundary (not between letters) is left as-is,
        # and will fail validation — OCR garbage should not be silently name-ified.
        with pytest.raises(ValidationError):
            PersonName.from_ocr_text("NGUYEN VAN 5")


class TestNfcNfdEquivalence:
    """⭐ Mandatory test case (§8.3.6): NFC and NFD input must give identical results."""

    @pytest.mark.parametrize("name", ["NGUYỄN VĂN AN", "TRẦN THỊ BÍCH NGỌC", "ĐẶNG QUỐC VIỆT"])
    def test_nfc_and_nfd_give_same_result(self, name: str) -> None:
        nfc_form = unicodedata.normalize("NFC", name)
        nfd_form = unicodedata.normalize("NFD", name)
        assert PersonName.from_raw(nfc_form).value == PersonName.from_raw(nfd_form).value


@given(st.sampled_from(["NGUYỄN VĂN AN", "TRẦN THỊ BÍCH NGỌC", "ĐẶNG QUỐC VIỆT", "HỒ CHÍ MINH"]))
def test_property_nfc_nfd_equivalence(name: str) -> None:
    """Property #5 (§8.11): same result for NFC and NFD forms of the same name."""
    nfc_form = unicodedata.normalize("NFC", name)
    nfd_form = unicodedata.normalize("NFD", name)
    assert PersonName.from_raw(nfc_form).value == PersonName.from_raw(nfd_form).value
