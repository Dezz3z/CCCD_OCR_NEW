"""Tests for `issue_place_shape` — tier 5, the opening-letters discriminator.

⭐ The `REAL_READINGS` and `REAL_OTHER_LINES` lists are not invented inputs.
They are the actual strings PaddleOCR produced on the user's 46 photos, captured
2026-08-10, and they are what turns "22/22 and 0/752" from a claim in a docstring
into something that fails the build when it stops being true.
"""
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from cocas.domain.services.issue_place_shape import (
    CONF_CORROBORATED,
    CONF_HEAD_ONLY,
    DECISIVE_SCORE,
    ShapeVerdict,
    discriminate,
)
from cocas.domain.value_objects.issue_place import BO_CONG_AN, CUC_CANH_SAT_QLHC_TTXH

# Every distinct `issue_place` reading in the sample. The 2021 card prints
# `CỤC TRƯỞNG CỤC CẢNH SÁT…`; the recognizer varies only in where it puts the
# word breaks and how it renders the horn diacritic of `TRƯỞNG`.
REAL_READINGS_CUC = [
    "CUC TRUONG CUC CANH SAT",
    "CUC TRUO'NG CUC CANH SAT",
    "CUC TRU'O'NG CUC CANH SAT",
    "CUCTRUO'NG CUC CANHSAT",
    "CUCTRUONG CUC CANHSAT",
    "CUCTRUONG CUC CANH SAT",
    "CUC TRUONG CUCCANH SAT",
    "CUCTRUO'NG CUC CANH SAT",
    "CUCTRUO'NG CUCCANH SAT",
    "CUCTRUONG CUCCANH SAT",
    "S CUC TRUONG CUC CANH SAT",  # ⭐ stray 1-letter glyph ahead of the name
]

REAL_READINGS_BO = [
    "BO C0NG AI/werYo ruc",  # ⭐ `Ô`→`0` and `N`→`I`, plus noise from the line below
    "BO CONGAN/MIMISIRYOFRUBLESECORITY",  # the English subtitle, glued on
]

# Lines the recognizer produced elsewhere on the same cards. None may ever
# produce a verdict — this is the half of the measurement that keeps tier 5 from
# being a machine for labelling arbitrary text.
REAL_OTHER_LINES = [
    "CONG HOA XA HOI CHU NGHIAVIETNAM",
    "CONG HOAXAHOI CHU NGHiA VIET NAM",
    "CAN CUOC CONG DAN",
    "CAN CU'O'C",
    "CANCU'OC CONG DAN",
    "CDIREGTORGENERALOF-THEPOLICEDEPARTMENT",
    "C6 gia tn den:18/09/2042",
    "C6 gia ri gan:01/022044",
    "CCANH",
    "CONC",
    "CONG",
    "BUI VAN LONG",
    "BUI<<VAN<LONG<<<<<<E<",
    "Binh Duong.BinhSan,Quang Ngai",
    "8201043M4201045VNM<<<<<<<<8",
    "Bó Trach, Quäng Binh",  # ⭐ the closest call in the sample — see below
]


class TestRealReadings:
    """⭐ 22/22 on the sample, every one of them at full confidence."""

    @pytest.mark.parametrize("raw", REAL_READINGS_CUC)
    def test_cuc_readings(self, raw: str) -> None:
        verdict = discriminate(raw)
        assert verdict.value == CUC_CANH_SAT_QLHC_TTXH
        assert verdict.confidence == CONF_CORROBORATED

    @pytest.mark.parametrize("raw", REAL_READINGS_BO)
    def test_bo_readings(self, raw: str) -> None:
        verdict = discriminate(raw)
        assert verdict.value == BO_CONG_AN
        assert verdict.confidence == CONF_CORROBORATED

    def test_merged_tokens_still_decide(self) -> None:
        """⭐ The case that defeats tiers 3 and 4 at the same time.

        `CUCTRUONG CUCCANH SAT` leaves `token_set_ratio` an intersection of one
        word and leaves the keyword tier without its `CUC` token, so both
        whole-string tiers return nothing. The head is untouched.
        """
        verdict = discriminate("CUCTRUONG CUCCANH SAT")
        assert verdict.value == CUC_CANH_SAT_QLHC_TTXH
        assert verdict.head == "CUC"

    def test_leading_stray_glyph_is_dropped(self) -> None:
        assert discriminate("S CUC TRUONG CUC CANH SAT").head == "CUC"

    def test_digit_inside_the_word_does_not_reach_the_head(self) -> None:
        assert discriminate("BO C0NG AI").head == "BOC"


class TestCorroboration:
    """The first word's length — the part of the length idea that survived."""

    def test_agreement_earns_the_higher_number(self) -> None:
        verdict = discriminate("BO CONG AN")
        assert verdict.first_word_agrees
        assert verdict.confidence == CONF_CORROBORATED

    def test_head_alone_when_the_merge_makes_length_lie(self) -> None:
        """⭐ `BOCONGAN` as one token votes 'long' — 8 letters — against a head
        that says `BỘ CÔNG AN`. The head is right and still wins; the
        disagreement costs confidence, not the answer."""
        verdict = discriminate("BOCONGAN")
        assert verdict.value == BO_CONG_AN
        assert not verdict.first_word_agrees
        assert verdict.confidence == CONF_HEAD_ONLY

    def test_the_bar_is_effectively_an_exact_head_match(self) -> None:
        """⚠️ `fuzz.ratio` on 3 characters is quantized to {0, 33.3, 66.7, 100},
        so nothing can land between the near-miss ceiling and a perfect match.
        Every verdict this module has ever produced scored exactly 100."""
        from rapidfuzz import fuzz

        assert {round(fuzz.ratio("CUC", other), 1) for other in ("CUC", "CUG", "CXC", "BOC")} == {
            100.0,
            66.7,
            33.3,
        }
        assert discriminate("CUC TRUONG CUC CANH SAT").head_score == 100.0
        assert discriminate("CUG TRUONG CUC CANH SAT").value is None


class TestPrecision:
    """0/752 on the sample: no other line on the card may produce a verdict."""

    @pytest.mark.parametrize("line", REAL_OTHER_LINES)
    def test_other_card_lines_yield_nothing(self, line: str) -> None:
        verdict = discriminate(line)
        assert verdict.value is None
        assert verdict.confidence == 0.0

    def test_the_closest_near_miss_stays_below_the_bar(self) -> None:
        """⭐ Why `DECISIVE_SCORE` is 80 and not 60.

        `Bố Trạch, Quảng Bình` is a place of origin printed on the front. Its
        head `BOT` scores 66.7 against `BOC` — the highest any non-authority
        line reaches in the whole sample, and the single number the threshold
        has to sit above.
        """
        from rapidfuzz import fuzz

        assert fuzz.ratio("BOT", "BOC") == pytest.approx(66.67, abs=0.01)
        assert fuzz.ratio("BOT", "BOC") < DECISIVE_SCORE
        assert discriminate("Bó Trach, Quäng Binh").value is None


class TestCanonicalInput:
    def test_canonical_bo(self) -> None:
        assert discriminate(BO_CONG_AN).value == BO_CONG_AN

    def test_canonical_cuc(self) -> None:
        assert discriminate(CUC_CANH_SAT_QLHC_TTXH).value == CUC_CANH_SAT_QLHC_TTXH

    def test_lowercase_and_diacritics(self) -> None:
        assert discriminate("bộ công an").value == BO_CONG_AN

    def test_partial_read_of_two_letters_still_decides(self) -> None:
        """A truncated `BO` is scored against `BOC[:2]`, not punished for length."""
        verdict = discriminate("BO")
        assert verdict.value == BO_CONG_AN
        assert verdict.head == "BO"


class TestNoVerdict:
    @pytest.mark.parametrize("raw", ["", "   ", "B", "C", "8", "///", "1234567890"])
    def test_too_little_to_go_on(self, raw: str) -> None:
        assert discriminate(raw).value is None

    def test_single_letter_never_decides(self) -> None:
        """⭐ `MIN_TOKEN_LETTERS`. `B` alone would score 100 against `BOC[:1]`
        with a 100-point margin; dropping short leading tokens is what stops
        tier 5 from answering for every line beginning with a B or a C."""
        assert discriminate("B").value is None
        assert discriminate("BO").value is not None

    def test_ambiguous_head_yields_nothing(self) -> None:
        # `CON` sits equidistant from both openings — a tie is not a verdict.
        assert discriminate("CONG HOA XA HOI").value is None


class TestShapeVerdictInvariants:
    def test_no_value_means_no_confidence(self) -> None:
        with pytest.raises(ValueError):
            ShapeVerdict(value=None, confidence=0.5)

    @given(st.text(max_size=80))
    @settings(max_examples=300, deadline=None)
    def test_property_never_a_third_value(self, raw: str) -> None:
        """Property #1 (§8.11) restated for tier 5, which can answer alone."""
        verdict = discriminate(raw)
        assert verdict.value in {BO_CONG_AN, CUC_CANH_SAT_QLHC_TTXH, None}
        assert 0.0 <= verdict.confidence <= 1.0
        assert verdict.value is not None or verdict.confidence == 0.0
