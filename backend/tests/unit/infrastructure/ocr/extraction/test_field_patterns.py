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

    def test_reads_a_date_whose_separators_the_recognizer_swallowed(self):
        """⭐ Real output from a Căn cước 2024 back; without this the issue date
        went unread entirely."""
        assert field_patterns.find_date("04062025") == "04/06/2025"

    def test_prefers_the_separated_date_when_both_shapes_are_present(self):
        """A bare run is far weaker evidence, so it is only a fallback."""
        assert field_patterns.find_date("04062025 cap 12/06/2026") == "12/06/2026"

    @pytest.mark.parametrize(
        "text",
        [
            "001087043408",  # 12 digits — the citizen id, not a date
            "0406202",  # 7 digits
            "040620251",  # 9 digits
            "04061899",  # year below the plausible range
        ],
    )
    def test_a_bare_digit_run_is_not_a_date_unless_it_looks_like_one(self, text):
        assert field_patterns.find_date(text) is None


class TestExpiry:
    def test_reads_a_date(self):
        assert field_patterns.find_expiry("Date of expiry 01/10/2042") == "01/10/2042"

    def test_reads_the_words_a_card_without_an_expiry_prints(self):
        assert field_patterns.find_expiry("Khong thoi han") == field_patterns.NO_EXPIRY

    def test_a_garbled_no_expiry_is_left_unread_rather_than_guessed(self):
        """⭐ `ovong thoi hg` IS the genuine value on a Căn cước 2024 back, and
        it is still refused — on purpose.

        Swept over all 774 recognized lines in the sample, it scores **69.8**
        while the highest-scoring line of any kind is a person's name
        (`PHAM THI PHU'O'NG THOA`, **76.2**). The true value sits *below* the
        noise, so no threshold accepts it without first accepting a name.
        `expiry_date` is optional; a blank the user fills in beats a confident
        wrong value.
        """
        assert field_patterns.find_expiry("ovong thoi hg") is None

    def test_a_name_never_passes_as_no_expiry(self):
        """The line that would break first if the threshold were lowered."""
        assert field_patterns.find_expiry("PHAM THI PHU'O'NG THOA") is None


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
    def test_rejects_digit_runs_fragments_and_headings(self, text):
        assert field_patterns.find_place(text) is None

    def test_keeps_a_letter_the_recognizer_mistook_for_a_single_digit(self):
        """⭐ `BỘ CÔNG AN` comes back as `BO C0NG AI`. Rejecting on *any* digit
        threw away the only reading of `issue_place` on a real card; a printed
        number always has a RUN of digits, a misread letter never does."""
        assert field_patterns.find_place("BO C0NG AI/werYo ruc") is not None

    def test_still_rejects_a_date_sharing_the_zone(self):
        """The reason the digit rule exists at all: `issue_place` sits one line
        below `expiry_date` on a Căn cước 2024 back."""
        assert field_patterns.find_place("06/08/2046") is None


class TestFinderCoverage:
    def test_every_field_key_has_a_finder(self):
        from cocas.domain.enums.field_key import FieldKey

        assert set(field_patterns.FINDERS) == set(FieldKey)
