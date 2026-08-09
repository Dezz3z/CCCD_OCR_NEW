"""Tests for IssuePlaceNormalizer (§12.5) — the 4-tier normalizer."""
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
