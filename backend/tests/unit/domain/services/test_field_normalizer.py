"""Tests for FieldNormalizer (§03 S9, §7.2 D1) — the stage that makes channels comparable."""
import unicodedata
import uuid

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from cocas.domain.enums.field_key import FieldKey
from cocas.domain.ports.persistence import AliasRecord
from cocas.domain.services.field_normalizer import (
    FLAG_DATE_REPAIRED,
    FLAG_ISSUE_PLACE_UNRECOGNIZED,
    FLAG_NO_EXPIRY,
    FLAG_UNPARSEABLE,
    REPAIRED_DATE_CONFIDENCE,
    FieldNormalizer,
    NormalizedValue,
)
from cocas.domain.services.issue_place_normalizer import IssuePlaceNormalizer
from cocas.domain.value_objects.id_card_dates import NO_EXPIRY_TEXT
from cocas.domain.value_objects.issue_place import BO_CONG_AN, CUC_CANH_SAT_QLHC_TTXH
from tests.fixtures.fake_ports import FakeAliasRepository

_ALIASES = [
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
        canonical_value=CUC_CANH_SAT_QLHC_TTXH,
        match_tier=4,
        assigned_confidence=0.60,
        keywords=("CUC", "CANH", "SAT"),
    ),
]


@pytest.fixture
def normalizer() -> FieldNormalizer:
    return FieldNormalizer(IssuePlaceNormalizer(FakeAliasRepository(_ALIASES)))


class TestIdNumber:
    @pytest.mark.asyncio
    async def test_plain_12_digits_pass_through(self, normalizer: FieldNormalizer) -> None:
        result = await normalizer.normalize(FieldKey.ID_NUMBER, "001199012345", 0.9)
        assert result.value == "001199012345"
        assert result.confidence == 0.9

    @pytest.mark.asyncio
    async def test_separators_and_letter_misreads_are_fixed(
        self, normalizer: FieldNormalizer
    ) -> None:
        result = await normalizer.normalize(FieldKey.ID_NUMBER, "OO1 199 O12345", 0.8)
        assert result.value == "001199012345"

    @pytest.mark.asyncio
    async def test_wrong_length_is_dropped_not_passed_through(
        self, normalizer: FieldNormalizer
    ) -> None:
        result = await normalizer.normalize(FieldKey.ID_NUMBER, "00119901234", 0.99)
        assert result.value is None
        assert result.confidence == 0.0
        assert FLAG_UNPARSEABLE in result.flags


class TestFullName:
    @pytest.mark.asyncio
    async def test_nfc_uppercase_and_collapsed(self, normalizer: FieldNormalizer) -> None:
        result = await normalizer.normalize(FieldKey.FULL_NAME, "  nguyễn   văn an ", 0.9)
        assert result.value == "NGUYỄN VĂN AN"

    @pytest.mark.asyncio
    async def test_nfd_and_nfc_input_agree(self, normalizer: FieldNormalizer) -> None:
        """⭐ Mandatory edge case (§8.11): both Unicode forms must normalize alike."""
        nfc = await normalizer.normalize(FieldKey.FULL_NAME, "NGUYỄN VĂN AN", 0.9)
        nfd = await normalizer.normalize(
            FieldKey.FULL_NAME, unicodedata.normalize("NFD", "NGUYỄN VĂN AN"), 0.9
        )
        assert nfc.value == nfd.value == "NGUYỄN VĂN AN"

    @pytest.mark.asyncio
    async def test_stray_characters_are_dropped_not_the_whole_name(
        self, normalizer: FieldNormalizer
    ) -> None:
        result = await normalizer.normalize(FieldKey.FULL_NAME, "NGUYỄN, VĂN AN.", 0.9)
        assert result.value == "NGUYỄN VĂN AN"

    @pytest.mark.asyncio
    async def test_zero_between_letters_becomes_o_not_deleted(
        self, normalizer: FieldNormalizer
    ) -> None:
        """⭐ Repair must run before out-of-charset filtering, or `H0ANG` → `HANG`."""
        result = await normalizer.normalize(FieldKey.FULL_NAME, "H0ANG VAN B", 0.9)
        assert result.value == "HOANG VAN B"

    @pytest.mark.asyncio
    async def test_digits_with_no_letter_twin_are_dropped_not_guessed(
        self, normalizer: FieldNormalizer
    ) -> None:
        # 3 and 4 have no entry in the digit→letter table, so they are removed
        # as out-of-charset rather than turned into a plausible-looking letter.
        result = await normalizer.normalize(FieldKey.FULL_NAME, "NGUY3N V4N AN", 0.9)
        assert result.value == "NGUYN VN AN"

    @pytest.mark.asyncio
    async def test_digits_only_yields_nothing(self, normalizer: FieldNormalizer) -> None:
        result = await normalizer.normalize(FieldKey.FULL_NAME, "123456", 0.9)
        assert result.value is None


class TestDates:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "raw",
        ["13/03/1987", "13-03-1987", "13.03.1987", "13031987", "13 / 03 / 1987"],
    )
    async def test_every_accepted_spelling_gives_one_iso_value(
        self, normalizer: FieldNormalizer, raw: str
    ) -> None:
        """⭐ The whole point of S9: three channels, three spellings, one value."""
        result = await normalizer.normalize(FieldKey.DATE_OF_BIRTH, raw, 0.9)
        assert result.value == "1987-03-13"

    @pytest.mark.asyncio
    async def test_leap_day_2024_is_valid(self, normalizer: FieldNormalizer) -> None:
        result = await normalizer.normalize(FieldKey.ISSUE_DATE, "29/02/2024", 0.9)
        assert result.value == "2024-02-29"

    @pytest.mark.asyncio
    async def test_leap_day_2023_is_rejected(self, normalizer: FieldNormalizer) -> None:
        result = await normalizer.normalize(FieldKey.ISSUE_DATE, "29/02/2023", 0.9)
        assert result.value is None

    @pytest.mark.asyncio
    async def test_year_outside_plausible_range_rejected(
        self, normalizer: FieldNormalizer
    ) -> None:
        result = await normalizer.normalize(FieldKey.DATE_OF_BIRTH, "13/03/1234", 0.9)
        assert result.value is None

    @pytest.mark.asyncio
    async def test_garbage_yields_nothing(self, normalizer: FieldNormalizer) -> None:
        result = await normalizer.normalize(FieldKey.DATE_OF_BIRTH, "Ngày sinh", 0.9)
        assert result.value is None
        assert result.confidence == 0.0


class TestDateRepair:
    @pytest.mark.asyncio
    async def test_impossible_month_repaired_when_exactly_one_reading_works(
        self, normalizer: FieldNormalizer
    ) -> None:
        # Month 16 cannot exist; 6→0 gives month 10, and 1→7 gives 76 which does not.
        result = await normalizer.normalize(FieldKey.ISSUE_DATE, "04/16/2025", 0.95)
        assert result.value == "2025-10-04"
        assert FLAG_DATE_REPAIRED in result.flags

    @pytest.mark.asyncio
    async def test_repaired_confidence_is_capped(self, normalizer: FieldNormalizer) -> None:
        result = await normalizer.normalize(FieldKey.ISSUE_DATE, "04/16/2025", 1.0)
        assert result.confidence == REPAIRED_DATE_CONFIDENCE

    @pytest.mark.asyncio
    async def test_repair_never_lifts_a_low_confidence(
        self, normalizer: FieldNormalizer
    ) -> None:
        result = await normalizer.normalize(FieldKey.ISSUE_DATE, "04/16/2025", 0.4)
        assert result.confidence == 0.4

    @pytest.mark.asyncio
    async def test_a_date_that_already_parses_is_never_touched(
        self, normalizer: FieldNormalizer
    ) -> None:
        """⭐ The safety argument for the repair pass: it only runs on failures.

        `01/01/1990` has three self-consistent readings under the confusion
        table; running repair on it would find several and reject the value the
        card actually printed.
        """
        result = await normalizer.normalize(FieldKey.DATE_OF_BIRTH, "01/01/1990", 0.9)
        assert result.value == "1990-01-01"
        assert FLAG_DATE_REPAIRED not in result.flags
        assert result.confidence == 0.9

    @pytest.mark.asyncio
    async def test_ambiguous_repair_is_refused(self, normalizer: FieldNormalizer) -> None:
        # Day and month both repair uniquely (00 → 06), but the year does not:
        # 1990 → 1996 is also in range, so two whole dates survive and neither
        # can be preferred. Refusing beats picking one at random.
        result = await normalizer.normalize(FieldKey.DATE_OF_BIRTH, "00/00/1990", 0.9)
        assert result.value is None


class TestExpiry:
    @pytest.mark.asyncio
    async def test_no_expiry_phrase_is_a_value_not_a_blank(
        self, normalizer: FieldNormalizer
    ) -> None:
        result = await normalizer.normalize(FieldKey.EXPIRY_DATE, NO_EXPIRY_TEXT, 0.9)
        assert result.value == NO_EXPIRY_TEXT
        assert result.is_no_expiry is True
        assert FLAG_NO_EXPIRY in result.flags

    @pytest.mark.asyncio
    async def test_no_expiry_without_diacritics_still_matches(
        self, normalizer: FieldNormalizer
    ) -> None:
        result = await normalizer.normalize(FieldKey.EXPIRY_DATE, "khong thoi han", 0.9)
        assert result.value == NO_EXPIRY_TEXT

    @pytest.mark.asyncio
    async def test_expiry_date_still_normalizes_as_a_date(
        self, normalizer: FieldNormalizer
    ) -> None:
        result = await normalizer.normalize(FieldKey.EXPIRY_DATE, "14052030", 0.98)
        assert result.value == "2030-05-14"
        assert result.is_no_expiry is False


class TestIssuePlace:
    @pytest.mark.asyncio
    async def test_exact_match_after_folding_diacritics(
        self, normalizer: FieldNormalizer
    ) -> None:
        result = await normalizer.normalize(FieldKey.ISSUE_PLACE, "BO CONG AN", 0.9)
        assert result.value == BO_CONG_AN
        assert result.tier == 1

    @pytest.mark.asyncio
    async def test_confidence_is_the_weaker_of_the_two_steps(
        self, normalizer: FieldNormalizer
    ) -> None:
        result = await normalizer.normalize(FieldKey.ISSUE_PLACE, "BCA", 0.70)
        assert result.value == BO_CONG_AN
        assert result.confidence == 0.70  # alias says 0.95, the reading says 0.70

    @pytest.mark.asyncio
    async def test_unrecognized_place_is_dropped_and_flagged(
        self, normalizer: FieldNormalizer
    ) -> None:
        result = await normalizer.normalize(FieldKey.ISSUE_PLACE, "SỞ TƯ PHÁP HÀ NỘI", 0.99)
        assert result.value is None
        assert result.confidence == 0.0
        assert FLAG_ISSUE_PLACE_UNRECOGNIZED in result.flags


class TestChannelHelper:
    @pytest.mark.asyncio
    async def test_one_confidence_covers_the_whole_block(
        self, normalizer: FieldNormalizer
    ) -> None:
        result = await normalizer.normalize_channel(
            {
                FieldKey.ID_NUMBER: "001199012345",
                FieldKey.DATE_OF_BIRTH: "13031987",
                FieldKey.FULL_NAME: "NGUYỄN VĂN AN",
            },
            0.98,
        )
        assert result[FieldKey.ID_NUMBER].value == "001199012345"
        assert result[FieldKey.DATE_OF_BIRTH].value == "1987-03-13"
        assert all(v.confidence == 0.98 for v in result.values())

    @pytest.mark.asyncio
    async def test_qr_and_mrz_agree_after_normalization(
        self, normalizer: FieldNormalizer
    ) -> None:
        """⭐ The regression this module exists to prevent (see module docstring)."""
        qr = await normalizer.normalize(FieldKey.DATE_OF_BIRTH, "13031987", 1.0)
        mrz = await normalizer.normalize(FieldKey.DATE_OF_BIRTH, "13031987", 0.98)
        ocr = await normalizer.normalize(FieldKey.DATE_OF_BIRTH, "13/03/1987", 0.86)
        assert qr.value == mrz.value == ocr.value


class TestInvariants:
    @pytest.mark.asyncio
    async def test_empty_input_never_raises(self, normalizer: FieldNormalizer) -> None:
        for key in FieldKey:
            assert (await normalizer.normalize(key, None, 0.9)).value is None
            assert (await normalizer.normalize(key, "   ", 0.9)).value is None

    def test_none_value_forces_zero_confidence(self) -> None:
        with pytest.raises(ValueError):
            NormalizedValue(value=None, confidence=0.5)


@given(
    text=st.text(max_size=40),
    confidence=st.floats(min_value=-5.0, max_value=5.0, allow_nan=False),
    key=st.sampled_from(list(FieldKey)),
)
@settings(max_examples=200, deadline=None)
@pytest.mark.asyncio
async def test_property_never_raises_and_confidence_stays_in_bounds(
    text: str, confidence: float, key: FieldKey
) -> None:
    """Any text, any confidence: a value in canonical form or nothing — never an exception."""
    normalizer = FieldNormalizer(IssuePlaceNormalizer(FakeAliasRepository(_ALIASES)))
    result = await normalizer.normalize(key, text, confidence)
    assert 0.0 <= result.confidence <= 1.0
    if result.value is None:
        assert result.confidence == 0.0
    if key is FieldKey.ISSUE_PLACE:
        assert result.value in {None, BO_CONG_AN, CUC_CANH_SAT_QLHC_TTXH}
