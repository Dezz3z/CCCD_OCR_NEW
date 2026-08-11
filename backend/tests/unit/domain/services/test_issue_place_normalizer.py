"""Tests for IssuePlaceNormalizer (§12.5) — the 5-tier normalizer."""
import uuid

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from cocas.domain.ports.persistence import AliasRecord
from cocas.domain.services.issue_place_normalizer import IssuePlaceNormalizer
from cocas.domain.value_objects.issue_place import BO_CONG_AN, CUC_CANH_SAT_QLHC_TTXH
from tests.fixtures.fake_ports import FakeAliasRepository

# Mirrors the seed data in docs/design/04-co-so-du-lieu.md §4.4.14.
_SEED_ALIASES = [
    AliasRecord(
        id=uuid.uuid4(),
        field_key="issue_place",
        canonical_value=BO_CONG_AN,
        match_tier=2,
        assigned_confidence=0.95,
        alias_normalized="BCA",
    ),
    AliasRecord(
        id=uuid.uuid4(),
        field_key="issue_place",
        canonical_value=BO_CONG_AN,
        match_tier=2,
        assigned_confidence=0.90,
        alias_normalized="B CONG AN",
    ),
    AliasRecord(
        id=uuid.uuid4(),
        field_key="issue_place",
        canonical_value=BO_CONG_AN,
        match_tier=2,
        assigned_confidence=0.90,
        alias_normalized="BO CONGAN",
    ),
    AliasRecord(
        id=uuid.uuid4(),
        field_key="issue_place",
        canonical_value=CUC_CANH_SAT_QLHC_TTXH,
        match_tier=2,
        assigned_confidence=0.95,
        alias_normalized="CUC CS QLHC VE TTXH",
    ),
    AliasRecord(
        id=uuid.uuid4(),
        field_key="issue_place",
        canonical_value=BO_CONG_AN,
        match_tier=4,
        assigned_confidence=0.60,
        keywords=("BO", "CONG", "AN"),
    ),
    AliasRecord(
        id=uuid.uuid4(),
        field_key="issue_place",
        canonical_value=CUC_CANH_SAT_QLHC_TTXH,
        match_tier=4,
        assigned_confidence=0.60,
        keywords=("CUC", "CANH", "SAT"),
    ),
]


def _make_normalizer(aliases: list[AliasRecord] | None = None) -> IssuePlaceNormalizer:
    repo = FakeAliasRepository(aliases if aliases is not None else _SEED_ALIASES)
    return IssuePlaceNormalizer(repo)


class TestTier1ExactStripped:
    async def test_already_canonical(self) -> None:
        outcome = await _make_normalizer().normalize(BO_CONG_AN)
        assert outcome.value == BO_CONG_AN
        assert outcome.tier == 1
        assert outcome.confidence == 1.0

    async def test_diacritics_stripped_input(self) -> None:
        outcome = await _make_normalizer().normalize("BO CONG AN")
        assert outcome.value == BO_CONG_AN
        assert outcome.tier == 1

    async def test_lowercase_input(self) -> None:
        outcome = await _make_normalizer().normalize("bộ công an")
        assert outcome.value == BO_CONG_AN
        assert outcome.tier == 1

    async def test_extra_whitespace(self) -> None:
        outcome = await _make_normalizer().normalize("  BỘ   CÔNG   AN  ")
        assert outcome.value == BO_CONG_AN
        assert outcome.tier == 1

    async def test_second_canonical_value(self) -> None:
        outcome = await _make_normalizer().normalize(CUC_CANH_SAT_QLHC_TTXH)
        assert outcome.value == CUC_CANH_SAT_QLHC_TTXH
        assert outcome.tier == 1


class TestTier2Alias:
    async def test_known_abbreviation(self) -> None:
        outcome = await _make_normalizer().normalize("BCA")
        assert outcome.value == BO_CONG_AN
        assert outcome.tier == 2
        assert outcome.confidence == 0.95
        assert outcome.matched_alias_id is not None

    async def test_alias_with_diacritics_in_input(self) -> None:
        outcome = await _make_normalizer().normalize("cục cs qlhc về ttxh")
        assert outcome.value == CUC_CANH_SAT_QLHC_TTXH
        assert outcome.tier == 2


class TestTier3Fuzzy:
    async def test_close_typo_high_confidence(self) -> None:
        # "B CONG AN" is a seeded alias; a near-miss of it should fuzzy-match.
        outcome = await _make_normalizer().normalize("B CONGAN")
        assert outcome.value == BO_CONG_AN
        assert outcome.tier in (2, 3)
        assert outcome.confidence >= 0.65


class TestTier4Keyword:
    async def test_keywords_present_in_any_order(self) -> None:
        # ⭐ Isolated from the tier-2/3 aliases: "B CONG AN" would otherwise
        # fuzzy-match (tier 3) any text containing these same 3 keywords,
        # since token_set_ratio is lenient about extra surrounding words.
        keyword_only_alias = AliasRecord(
            id=uuid.uuid4(),
            field_key="issue_place",
            canonical_value=BO_CONG_AN,
            match_tier=4,
            assigned_confidence=0.60,
            keywords=("BO", "CONG", "AN"),
        )
        outcome = await _make_normalizer([keyword_only_alias]).normalize(
            "TRICH YEU NOI DUNG KHONG RO RANG NHUNG CO NHAC DEN BO CONG AN O DAY"
        )
        assert outcome.value == BO_CONG_AN
        assert outcome.tier == 4
        assert outcome.confidence == 0.60


class TestTier5Shape:
    """⭐ The opening-letters tier, and where it sits in the order."""

    async def test_the_line_the_2021_card_actually_prints(self) -> None:
        """⭐ The reading that used to come back empty.

        `CỤC TRƯỞNG CỤC CẢNH SÁT` is what 18 of the 22 photos carrying this
        field produce. It is not a canonical value, not a seeded alias, and its
        merged variants defeat both whole-string tiers.
        """
        outcome = await _make_normalizer().normalize("CUC TRUONG CUC CANH SAT")
        assert outcome.value == CUC_CANH_SAT_QLHC_TTXH
        assert outcome.tier == 5
        assert outcome.confidence == 0.92

    async def test_merged_tokens_that_defeat_tiers_3_and_4(self) -> None:
        outcome = await _make_normalizer().normalize("CUCTRUONG CUCCANH SAT")
        assert outcome.value == CUC_CANH_SAT_QLHC_TTXH
        assert outcome.tier == 5

    async def test_clears_the_review_threshold(self) -> None:
        """The point of the whole tier: 0.92 > fusion's 0.85, so the field
        stops arriving pre-flagged for manual review on every single card."""
        from cocas.domain.services.field_fusion_service import DEFAULT_REVIEW_THRESHOLD

        outcome = await _make_normalizer().normalize("CUC TRUONG CUC CANH SAT")
        assert outcome.confidence >= DEFAULT_REVIEW_THRESHOLD

    async def test_tier_1_still_wins(self) -> None:
        outcome = await _make_normalizer().normalize(BO_CONG_AN)
        assert outcome.tier == 1
        assert outcome.confidence == 1.0

    async def test_curated_alias_beats_the_heuristic_even_when_it_scores_lower(self) -> None:
        """⭐ `BO CONGAN` is a seeded tier-2 alias at 0.90 and also a perfect
        head match worth 0.92. The exact alias wins anyway: a curated row is a
        statement about this specific string, the head is an inference about
        every string starting the same way."""
        outcome = await _make_normalizer().normalize("BO CONGAN")
        assert outcome.tier == 2
        assert outcome.confidence == 0.90

    async def test_shape_runs_before_the_whole_string_tiers(self) -> None:
        # Tier 3 would reach this via `CUC CS QLHC VE TTXH`; tier 5 gets there
        # first and with a higher score.
        outcome = await _make_normalizer().normalize("CUC CS QLHC VE TTX")
        assert outcome.value == CUC_CANH_SAT_QLHC_TTXH
        assert outcome.tier == 5

    async def test_no_head_signal_falls_through_to_the_lower_tiers(self) -> None:
        outcome = await _make_normalizer().normalize(
            "TRICH YEU NOI DUNG KHONG RO RANG NHUNG CO NHAC DEN BO CONG AN O DAY"
        )
        assert outcome.value == BO_CONG_AN
        assert outcome.tier in (3, 4)


class TestNoMatch:
    async def test_unrelated_text(self) -> None:
        outcome = await _make_normalizer(aliases=[]).normalize("XYZ HOAN TOAN KHONG LIEN QUAN")
        assert outcome.value is None
        assert outcome.confidence == 0.0

    async def test_empty_string(self) -> None:
        outcome = await _make_normalizer(aliases=[]).normalize("")
        assert outcome.value is None

    async def test_to_issue_place_none_when_no_match(self) -> None:
        outcome = await _make_normalizer(aliases=[]).normalize("")
        assert outcome.to_issue_place() is None

    async def test_to_issue_place_wraps_value(self) -> None:
        outcome = await _make_normalizer().normalize(BO_CONG_AN)
        place = outcome.to_issue_place()
        assert place is not None
        assert place.value == BO_CONG_AN


class TestMandatoryInvariant:
    """⭐ §12.5: 'Không tồn tại đường nào trả về giá trị thứ ba.'"""

    @pytest.mark.parametrize(
        "raw",
        [
            BO_CONG_AN, CUC_CANH_SAT_QLHC_TTXH, "BCA", "xyz", "", "123456",
            "Bộ Công An", "cục công an", "random garbage text here",
        ],
    )
    async def test_always_one_of_three_allowed_values(self, raw: str) -> None:
        outcome = await _make_normalizer().normalize(raw)
        assert outcome.value in {BO_CONG_AN, CUC_CANH_SAT_QLHC_TTXH, None}

    @given(st.text(max_size=60))
    @settings(max_examples=100, deadline=None)
    def test_property_any_string_yields_allowed_value(self, raw: str) -> None:
        """Property #1 (§8.11): normalize(ANY string) is always one of 3 allowed values."""
        import asyncio

        outcome = asyncio.run(_make_normalizer().normalize(raw))
        assert outcome.value in {BO_CONG_AN, CUC_CANH_SAT_QLHC_TTXH, None}
        assert 0.0 <= outcome.confidence <= 1.0
