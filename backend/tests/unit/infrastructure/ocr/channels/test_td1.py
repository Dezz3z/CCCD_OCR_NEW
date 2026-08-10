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


class TestLineClassification:
    """⭐ Slots are decided by structure, never by the order lines were found.

    Recognition regularly misses one of the three lines. Assuming "the first
    line found is line 1" puts the name line in line 1's slot, where its
    letters get force-digitized into a citizen id — six confident wrong values
    out of one missed line. Measured on real cards before this existed.
    """

    def test_recognizes_each_line_of_a_real_block(self):
        assert [td1.classify_line(line) for line in REAL_MRZ_LINES] == [0, 1, 2]

    def test_a_name_line_never_lands_in_the_id_slot(self):
        assert td1.classify_line("TRAN<<THI<THUY<DUONG<<<<<<<<<<") == 2

    def test_tolerates_a_misread_sex_character(self):
        """A real card came back with `E` where `F` is printed."""
        assert td1.classify_line("9706305E3706303VNM<<<<<<<<<<<2") == 1

    def test_an_address_line_never_reaches_a_data_slot(self):
        """The label above the MRZ has no digits, so it can only look like a
        name line — never like line 1 or line 2, the two that carry fields."""
        assert td1.classify_line("Noi thuong tru / Place of residence") == 2

    @pytest.mark.parametrize("line", ["", "ID", "IDVNM17900"])
    def test_rejects_lines_too_short_to_be_mrz(self, line):
        assert td1.classify_line(line) is None


class TestSelectLines:
    def test_picks_the_block_out_of_surrounding_text(self):
        noise = "Noi thuong tru / Place of residence\nPhuoc Long, Nha Trang\n"
        assert td1.select_lines(noise + "\n".join(REAL_MRZ_LINES)) == REAL_MRZ_LINES

    def test_splits_a_block_the_recognizer_returned_as_one_run(self):
        assert td1.select_lines("".join(REAL_MRZ_LINES)) == REAL_MRZ_LINES

    def test_fills_a_missing_name_line_rather_than_shifting_the_others(self):
        selected = td1.select_lines("\n".join(REAL_MRZ_LINES[:2]))
        assert selected is not None
        assert selected[:2] == REAL_MRZ_LINES[:2]
        assert selected[2] == td1.FILLER * td1.LINE_LENGTH

    def test_refuses_when_the_two_data_lines_are_not_both_present(self):
        """⭐ Lines 1 and 2 carry every field MRZ contributes — without them
        there is nothing to report, and guessing is worse than silence."""
        assert td1.select_lines(REAL_MRZ_LINES[2]) is None

    def test_ignores_mixed_case_prose(self):
        assert td1.select_lines("Dac diem nhan dang / Personal identification") is None


class TestTailRealignment:
    """⭐ The single largest cause of checksum failure on real cards.

    A TD1 line ends with a long run of `<` and then one check digit. Recognizers
    miscount identical glyph runs, so that digit lands a few columns early or is
    swallowed whole — while every data column is read correctly.
    """

    def test_recovers_a_check_digit_pushed_into_the_filler_run(self):
        damaged = list(REAL_MRZ_LINES)
        damaged[1] = "7902273F3902275VNM<<<<<<<<2<<<"
        assert td1.parse(damaged).composite_valid is True

    def test_leaves_a_correctly_placed_check_digit_alone(self):
        assert td1.parse(list(REAL_MRZ_LINES)).lines == REAL_MRZ_LINES

    def test_does_not_guess_when_the_tail_holds_several_digits(self):
        damaged = list(REAL_MRZ_LINES)
        damaged[1] = "7902273F3902275VNM<<<<<7<<2<<"[:30].ljust(30, "<")
        assert td1.parse(damaged).lines[1].endswith("<")


class TestCompositeCheck:
    def test_a_clean_block_satisfies_it(self):
        assert td1.composite_check_passes(list(REAL_MRZ_LINES)) is True

    def test_group_checks_pass_without_it(self):
        """A block missing only its whole-block digit is still trustworthy."""
        damaged = list(REAL_MRZ_LINES)
        damaged[1] = damaged[1][:29] + td1.FILLER
        assert td1.group_checks_pass(damaged) is True
        assert td1.composite_check_passes(damaged) is False


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
