"""Field value shapes — the last gate before a value reaches fusion (§7.4.6).

⭐ Every input string below is real recognizer output from a CCCD photo,
including its mistakes. A pattern tuned against clean text is a pattern that
has never met this engine.
"""
from __future__ import annotations

import pytest

from cocas.infrastructure.ocr.extraction import field_patterns


class TestIdNumber:
    def test_reads_a_clean_twelve_digit_number(self):
        assert field_patterns.find_id_number("001087043408") == "001087043408"

    def test_reads_the_value_beside_its_label(self):
        assert field_patterns.find_id_number("S61No.: 048179002546") == "048179002546"

    def test_closes_gaps_the_recognizer_opens_in_a_digit_run(self):
        assert field_patterns.find_id_number("001 087 043408") == "001087043408"

    @pytest.mark.parametrize(
        "text", ["00108704340", "0010870434081", "13/03/1987", "BUI VAN LONG"]
    )
    def test_rejects_anything_that_is_not_exactly_twelve_digits(self, text):
        assert field_patterns.find_id_number(text) is None


class TestDate:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("13/03/1987", "13/03/1987"),
            ("Ngay sinh/Date of birth. 27/02/1979", "27/02/1979"),
            ("co gia nden27/02/2039", "27/02/2039"),
            ("C6 gia tr aén: 28/08/2038", "28/08/2038"),
            ("18.09.2042", "18/09/2042"),
        ],
    )
    def test_finds_a_date_however_the_recognizer_mangled_the_line(self, text, expected):
        assert field_patterns.find_date(text) == expected

    @pytest.mark.parametrize("text", ["32/01/2020", "13/13/2020", "001087043408"])
    def test_rejects_an_impossible_date(self, text):
        assert field_patterns.find_date(text) is None


class TestExpiry:
    def test_reads_a_date(self):
        assert field_patterns.find_expiry("Date of expiry 01/10/2042") == "01/10/2042"

    def test_reads_the_words_a_card_without_an_expiry_prints(self):
        assert field_patterns.find_expiry("Khong thoi han") == field_patterns.NO_EXPIRY

    def test_a_garbled_fragment_no_longer_passes_as_no_expiry(self):
        """⭐ Real recognizer output that scored exactly 80 against the phrase."""
        assert field_patterns.find_expiry("ovong thoi hg") is None


class TestName:
    def test_reads_a_name(self):
        assert field_patterns.find_name("BUI VAN LONG") == "BUI VAN LONG"

    def test_strips_a_label_sharing_the_line(self):
        assert field_patterns.find_name("Full name: Bui Van Long") == "BUI VAN LONG"

    def test_keeps_the_apostrophe_form_the_recognizer_emits_for_a_horn(self):
        assert field_patterns.find_name("QUACH THI NAMPHU'ONG") is not None

    @pytest.mark.parametrize(
        "text",
        [
            "Citizen Identity Card",
            "CAN CU'O'C CONG DAN",
            "CONG HOAXAHOI CHU NGHIAVIET NAM",
            "Independence-Freedom-Happiness",
        ],
    )
    def test_refuses_text_the_card_prints_on_every_copy(self, text):
        """⭐ Measured failure: a zone off by one line handed
        `CITIZEN IDENTITY CARD` to fusion as a customer's name."""
        assert field_patterns.find_name(text) is None

    @pytest.mark.parametrize("text", ["LONG", "13/03/1987", "Hova ten/ Full name."])
    def test_rejects_a_single_word_a_date_or_a_label(self, text):
        assert field_patterns.find_name(text) is None


class TestPlace:
    def test_reads_the_issuing_authority(self):
        value = field_patterns.find_place("CUC TRUONG CUC CANH SAT")
        assert value == "CUC TRUONG CUC CANH SAT"

    def test_the_authority_is_not_treated_as_boilerplate(self):
        """⭐ Every card prints it — but on a CCCD it IS the `issue_place`."""
        assert field_patterns.find_place("CUC TRUONG CUC CANH SAT") is not None

    @pytest.mark.parametrize("text", ["Ha Noi 2022", "short", "Personal identification"])
    def test_rejects_digits_fragments_and_headings(self, text):
        assert field_patterns.find_place(text) is None


class TestFinderCoverage:
    def test_every_field_key_has_a_finder(self):
        from cocas.domain.enums.field_key import FieldKey

        assert set(field_patterns.FINDERS) == set(FieldKey)
