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
        """Transcribed from a real card, where it scored exactly 80."""
        assert text_matching.similarity("ovong thoi hg", "KHÔNG THỜI HẠN") < 80


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


class TestBestMatch:
    def test_reports_which_anchor_won(self):
        anchor, score = text_matching.best_match(
            "Ngay sinh/Date of birth.", ["Full name", "Ngày sinh"]
        )
        assert anchor == "Ngày sinh"
        assert score >= text_matching.FIELD_ANCHOR_THRESHOLD

    def test_empty_text_matches_nothing(self):
        assert text_matching.best_match("", ["Full name"]) == (None, 0.0)
