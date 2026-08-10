"""Fuzzy matching of card text — folding and the length-coverage guard.

Every number here is anchored to something a real card produced; the fragments
are transcribed from recognizer output, not invented.
"""
from __future__ import annotations

import pytest

from cocas.infrastructure.ocr import text_matching


class TestFolding:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("CỘNG HÒA XÃ HỘI", "CONG HOA XA HOI"),
            ("Đặng Duy Nghĩa", "DANG DUY NGHIA"),
            ("  spaced   out  ", "SPACED OUT"),
        ],
    )
    def test_strips_diacritics_and_case(self, raw, expected):
        assert text_matching.fold(raw) == expected

    def test_drops_the_apostrophe_the_recognizer_emits_for_a_horn(self):
        """⭐ `CĂN CƯỚC` comes back as `CAN CU'O'C`: the latin model has no
        output class for ơ/ư and renders the horn as a trailing quote."""
        assert text_matching.fold("CAN CU'O'C CONG DAN") == "CAN CUOC CONG DAN"

    def test_folds_the_two_spellings_of_a_card_title_together(self):
        assert text_matching.fold("CAN CU'O'C CONG DAN") == text_matching.fold(
            "Căn cước công dân"
        )


class TestLengthCoverage:
    """⭐ The guard that stopped 6 of 46 inverted cards being called upright.

    `partial_ratio` scores the best-matching substring, so any fragment the
    anchor happens to contain scores 100. Coverage scales that by how much of
    the anchor the text could possibly account for.
    """

    def test_a_two_character_fragment_does_not_match_a_long_anchor(self):
        score = text_matching.similarity("ON", "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM")
        assert score < 10

    def test_the_full_phrase_still_matches(self):
        score = text_matching.similarity(
            "CONG HOAXAHOI CHU NGHIAVIET NAM", "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM"
        )
        assert score >= text_matching.BOILERPLATE_THRESHOLD

    def test_a_label_inside_a_longer_line_still_matches(self):
        """The recognizer returns label and value as one line."""
        score = text_matching.similarity("Hova ten/ Full name.", "Full name")
        assert score == pytest.approx(100.0)

    def test_a_garbled_fragment_no_longer_reaches_the_no_expiry_phrase(self):
        """Transcribed from a real Căn cước 2024 back, where it measures 69.8 —
        *below* the 76.2 a person's name reaches against the same phrase."""
        garbled = text_matching.similarity("ovong thoi hg", "KHÔNG THỜI HẠN")
        a_name = text_matching.similarity("PHAM THI PHU'O'NG THOA", "KHÔNG THỜI HẠN")
        assert garbled < a_name < text_matching.BOILERPLATE_THRESHOLD


class TestBoilerplate:
    @pytest.mark.parametrize(
        "text",
        ["Citizen Identity Card", "CAN CU'OC CONG DAN", "Dac diem nhan dang"],
    )
    def test_recognizes_text_every_card_prints(self, text):
        assert text_matching.is_printed_boilerplate(text) is True

    @pytest.mark.parametrize("text", ["BUI VAN LONG", "VO HUYNH NGAN GIAO"])
    def test_a_persons_name_is_not_boilerplate(self, text):
        assert text_matching.is_printed_boilerplate(text) is False

    def test_the_issuing_authority_is_left_out_because_it_is_a_value(self):
        """⭐ Every card prints it, but on a CCCD it IS the `issue_place`."""
        assert (
            text_matching.is_printed_boilerplate("CUC TRUONG CUC CANH SAT") is False
        )

    def test_the_orientation_fingerprint_covers_only_top_of_card_phrases(self):
        """⭐ A phrase printed at the bottom moves into the search band when the
        card is flipped, so it fingerprints nothing."""
        folded = {text_matching.fold(item) for item in text_matching.CARD_TOP_FINGERPRINT}
        assert text_matching.fold("Nơi thường trú") not in folded
        assert text_matching.fold("Date of expiry") not in folded
        assert text_matching.fold("CĂN CƯỚC CÔNG DÂN") in folded


class TestSecondCardGeneration:
    """⭐ The 2024 `CĂN CƯỚC` renames most of what the 2021 card prints, and the
    longer 2021 phrases do not reach the shorter 2024 ones."""

    @pytest.mark.parametrize(
        ("shorter", "longer"),
        [
            ("CĂN CƯỚC", "CĂN CƯỚC CÔNG DÂN"),
            ("IDENTITY CARD", "Citizen Identity Card"),
        ],
    )
    def test_the_2021_phrase_does_not_cover_the_2024_one(self, shorter, longer):
        """Why the list had to grow rather than rely on what was already there:
        measured 50.0 and 63.2, both far under the threshold."""
        assert text_matching.similarity(shorter, longer) < text_matching.BOILERPLATE_THRESHOLD

    @pytest.mark.parametrize(
        "text",
        [
            "CAN CUOC",
            "IDENTITYCARD",
            "Södinhdanhca nhan/Personal identificationnumber",
            "Ho, chu dem va ten khai sinh/Ful name",
            "Not dang ky khai sint/`Place",
        ],
    )
    def test_recognizes_what_a_2024_card_prints(self, text):
        """Every string is real recognizer output from a Căn cước 2024."""
        assert text_matching.is_printed_boilerplate(text) is True

    def test_the_2024_authority_is_left_out_because_it_is_a_value(self):
        """⭐ Same rule as the 2021 authority: `BỘ CÔNG AN` IS `issue_place`, so
        listing it would make `find_place` discard the field."""
        assert text_matching.is_printed_boilerplate("BO CONG AN") is False

    def test_the_2024_top_phrases_joined_the_fingerprint(self):
        folded = {text_matching.fold(item) for item in text_matching.CARD_TOP_FINGERPRINT}
        assert text_matching.fold("CĂN CƯỚC") in folded
        assert text_matching.fold("Nơi đăng ký khai sinh") in folded

    def test_a_phrase_below_the_search_band_stays_out_of_the_fingerprint(self):
        """⭐ `Số định danh cá nhân` sits at y≈0.40 — outside the top strip the
        oracle reads — so it would contribute nothing either way up."""
        folded = {text_matching.fold(item) for item in text_matching.CARD_TOP_FINGERPRINT}
        assert text_matching.fold("Số định danh cá nhân") not in folded


class TestBestMatch:
    def test_reports_which_anchor_won(self):
        anchor, score = text_matching.best_match(
            "Ngay sinh/Date of birth.", ["Full name", "Ngày sinh"]
        )
        assert anchor == "Ngày sinh"
        assert score >= text_matching.FIELD_ANCHOR_THRESHOLD

    def test_empty_text_matches_nothing(self):
        assert text_matching.best_match("", ["Full name"]) == (None, 0.0)
