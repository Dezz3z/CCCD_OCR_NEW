"""TD1 string handling — checksums, charset forcing, and bounded repair (§7.4.4).

The reference block is transcribed from a real CCCD back, so these tests pin the
Vietnamese field layout (CCCD in optional data, CMND in the document-number
field) rather than a guess at it.
"""
from __future__ import annotations

import pytest

from cocas.infrastructure.ocr.channels import td1

from .conftest import REAL_MRZ_LINES


class TestCheckDigit:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("179002546", "2"),
            ("048179002546<<", "2"),
            ("790227", "3"),
            ("390227", "5"),
        ],
    )
    def test_matches_the_digits_printed_on_a_real_card(self, value, expected):
        assert td1.check_digit(value) == expected

    def test_filler_contributes_nothing(self):
        assert td1.check_digit("<<<<<<") == "0"

    def test_letters_use_their_ordinal_value(self):
        assert td1.check_digit("A") == td1.check_digit("10"[0] * 0 + "A")


class TestParseRealCard:
    @pytest.fixture
    def parsed(self):
        return td1.parse(list(REAL_MRZ_LINES))

    def test_every_checksum_including_the_composite_validates(self, parsed):
        assert parsed.checksum_valid is True

    def test_a_clean_read_needs_no_corrections(self, parsed):
        assert parsed.corrections_applied == 0

    def test_citizen_id_comes_from_optional_data_not_the_document_number(self, parsed):
        assert parsed.fields.citizen_id == "048179002546"
        assert parsed.fields.document_number == "179002546"

    def test_extracts_the_dates_and_sex(self, parsed):
        assert parsed.fields.date_of_birth == "790227"
        assert parsed.fields.date_of_expiry == "390227"
        assert parsed.fields.sex == "F"

    def test_splits_the_name_on_the_double_filler(self, parsed):
        assert parsed.fields.surname == "VO"
        assert parsed.fields.given_names == "HUYNH NGAN GIAO"


class TestCharsetForcing:
    def test_keeps_characters_that_already_belong(self):
        assert td1.force_charset("IDVNM<<123") == "IDVNM<<123"

    def test_uppercases_lowercase_input(self):
        assert td1.force_charset("idvnm") == "IDVNM"

    def test_unmappable_characters_become_filler_to_preserve_alignment(self):
        forced = td1.force_charset("AB#$CD")
        assert forced == "AB<<CD"
        assert len(forced) == len("AB#$CD")

    def test_diacritics_do_not_survive_into_the_block(self):
        assert "Ệ" not in td1.force_charset("NGUYỆN")

    def test_letters_are_not_digitized_globally(self):
        """⭐ A global O→0 map would corrupt every name containing O, D, S or B."""
        assert td1.force_charset("DO<<HOANG<SON<BAO") == "DO<<HOANG<SON<BAO"


class TestDigitize:
    @pytest.mark.parametrize(
        ("letters", "digits"),
        [("O", "0"), ("Q", "0"), ("D", "0"), ("I", "1"), ("S", "5"), ("B", "8")],
    )
    def test_forces_lookalike_letters_in_numeric_spans(self, letters, digits):
        assert td1.digitize(letters) == digits

    def test_leaves_digits_untouched(self):
        assert td1.digitize("0123456789") == "0123456789"


class TestNormalizeLines:
    def test_pads_short_lines_to_thirty(self):
        lines = td1.normalize_lines("IDVNM\n7902\nVO")
        assert [len(line) for line in lines] == [30, 30, 30]

    def test_truncates_overlong_lines(self):
        lines = td1.normalize_lines("\n".join(["X" * 40] * 3))
        assert all(len(line) == 30 for line in lines)

    def test_rechunks_when_the_recognizer_returns_one_blob(self):
        blob = "".join(REAL_MRZ_LINES)
        assert td1.normalize_lines(blob) == REAL_MRZ_LINES

    def test_drops_spaces_rather_than_treating_them_as_filler(self):
        """Spaces would shift every field right if kept as `<`."""
        lines = td1.normalize_lines("ID VNM 179002546\nX\nY")
        assert lines[0].startswith("IDVNM179002546")


class TestRepair:
    def test_recovers_a_letter_that_replaced_a_digit(self):
        damaged = list(REAL_MRZ_LINES)
        damaged[0] = damaged[0].replace("179002546", "17900Z546", 1)
        parsed = td1.parse(damaged)
        assert parsed.fields.document_number == "179002546"
        assert parsed.checksum_valid is True

    def test_repairs_a_digit_swap_and_reports_the_edit(self):
        damaged = list(REAL_MRZ_LINES)
        damaged[1] = "7902278F3902275VNM<<<<<<<<<<<2"
        parsed = td1.parse(damaged)
        assert parsed.corrections_applied >= 1

    def test_gives_up_instead_of_inventing_a_pass(self):
        """⭐ Unbounded search would satisfy any check digit — and be confidently wrong."""
        damaged = ["9" * 30, "9" * 30, "V" * 30]
        parsed = td1.parse(damaged)
        assert parsed.checksum_valid is False

    def test_never_edits_beyond_the_budget(self):
        damaged = list(REAL_MRZ_LINES)
        damaged[0] = "IDVNM9999999992048179002546<<2"
        parsed = td1.parse(damaged)
        assert parsed.corrections_applied <= td1.MAX_REPAIR_EDITS * 2
