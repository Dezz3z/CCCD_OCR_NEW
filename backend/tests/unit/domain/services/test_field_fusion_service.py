"""Tests for FieldFusionService (§12.6) — one class per merge rule."""
from hypothesis import given, settings
from hypothesis import strategies as st

from cocas.domain.enums.field_key import FieldKey
from cocas.domain.enums.field_source import FieldSource
from cocas.domain.services.field_fusion_service import (
    CONSENSUS_BONUS,
    CONTRADICTED_CONFIDENCE,
    FLAG_CARD_MISMATCH,
    FLAG_ID_INCONSISTENT,
    FLAG_SOURCE_CONFLICT,
    OCR_FIELD_FACTORS,
    Candidate,
    FieldFusionService,
    FusionContext,
)

_ALL_KEYS = list(FieldKey)

# `001 1 99 012345` — province 001, female born in the 1900s, birth year 1999.
VALID_ID = "001199012345"
MATCHING_BIRTH_DATE = "1999-05-14"


def fuse(candidates, context: FusionContext | None = None):
    return FieldFusionService().fuse(candidates, context or FusionContext())


class TestRule1AllSixKeys:
    def test_empty_input_still_yields_6_keys(self) -> None:
        assert set(fuse({}).keys()) == set(_ALL_KEYS)

    def test_partial_input_still_yields_6_keys(self) -> None:
        result = fuse({FieldKey.FULL_NAME: [Candidate("NGUYỄN VĂN AN", FieldSource.QR, 1.0)]})
        assert set(result.keys()) == set(_ALL_KEYS)


class TestNoneInvariant:
    def test_no_candidates_yields_none_and_zero_confidence(self) -> None:
        fused = fuse({})[FieldKey.FULL_NAME]
        assert fused.value is None
        assert fused.confidence == 0.0
        assert fused.source == FieldSource.NONE
        assert fused.needs_review is True

    def test_all_candidates_none_value_yields_none(self) -> None:
        result = fuse({FieldKey.FULL_NAME: [Candidate(None, FieldSource.OCR, 0.5)]})
        assert result[FieldKey.FULL_NAME].value is None
        assert result[FieldKey.FULL_NAME].source == FieldSource.NONE

    def test_empty_string_counts_as_no_value(self) -> None:
        result = fuse({FieldKey.FULL_NAME: [Candidate("", FieldSource.OCR, 0.9)]})
        assert result[FieldKey.FULL_NAME].value is None


class TestRule2SourcePriority:
    def test_qr_wins_over_ocr_when_they_disagree(self) -> None:
        result = fuse(
            {
                FieldKey.ID_NUMBER: [
                    Candidate(VALID_ID, FieldSource.QR, 0.95),
                    Candidate("001199099999", FieldSource.OCR, 0.90),
                ]
            }
        )
        assert result[FieldKey.ID_NUMBER].value == VALID_ID
        assert result[FieldKey.ID_NUMBER].source == FieldSource.QR

    def test_ocr_name_is_scaled_by_its_field_factor(self) -> None:
        """⭐ Rule 2's per-field factor — the latin model cannot spell a Vietnamese name."""
        result = fuse({FieldKey.FULL_NAME: [Candidate("NGUYEN VAN AN", FieldSource.OCR, 1.0)]})
        assert result[FieldKey.FULL_NAME].confidence == OCR_FIELD_FACTORS[FieldKey.FULL_NAME]
        assert result[FieldKey.FULL_NAME].needs_review is True

    def test_qr_is_not_scaled(self) -> None:
        result = fuse({FieldKey.FULL_NAME: [Candidate("NGUYỄN VĂN AN", FieldSource.QR, 1.0)]})
        assert result[FieldKey.FULL_NAME].confidence == 1.0

    def test_the_factor_can_be_overridden_from_configuration(self) -> None:
        context = FusionContext(ocr_field_factors={FieldKey.FULL_NAME: 1.0})
        result = fuse({FieldKey.FULL_NAME: [Candidate("AN VAN", FieldSource.OCR, 0.9)]}, context)
        assert result[FieldKey.FULL_NAME].confidence == 0.9

    def test_best_candidate_per_source_is_kept(self) -> None:
        result = fuse(
            {
                FieldKey.ISSUE_PLACE: [
                    Candidate("BỘ CÔNG AN", FieldSource.OCR, 0.40),
                    Candidate("BỘ CÔNG AN", FieldSource.OCR, 0.80),
                ]
            }
        )
        assert result[FieldKey.ISSUE_PLACE].confidence == 0.80


class TestRule3ConsensusBonus:
    def test_agreement_across_sources_boosts_confidence(self) -> None:
        result = fuse(
            {
                FieldKey.FULL_NAME: [
                    Candidate("NGUYỄN VĂN AN", FieldSource.QR, 0.80),
                    Candidate("NGUYỄN VĂN AN", FieldSource.MRZ, 0.80),
                ]
            }
        )
        assert result[FieldKey.FULL_NAME].confidence == 0.80 + CONSENSUS_BONUS
        assert result[FieldKey.FULL_NAME].agreement is True

    def test_three_sources_agreeing_get_two_bonuses(self) -> None:
        result = fuse(
            {
                FieldKey.DATE_OF_BIRTH: [
                    Candidate("1987-03-13", FieldSource.QR, 0.70),
                    Candidate("1987-03-13", FieldSource.MRZ, 0.70),
                    Candidate("1987-03-13", FieldSource.OCR, 0.70),
                ]
            }
        )
        assert result[FieldKey.DATE_OF_BIRTH].confidence == 0.70 + 2 * CONSENSUS_BONUS

    def test_a_single_source_gets_no_bonus_and_no_agreement(self) -> None:
        result = fuse({FieldKey.FULL_NAME: [Candidate("AN", FieldSource.QR, 0.80)]})
        assert result[FieldKey.FULL_NAME].confidence == 0.80
        assert result[FieldKey.FULL_NAME].agreement is False

    def test_confidence_never_exceeds_one(self) -> None:
        result = fuse(
            {
                FieldKey.FULL_NAME: [
                    Candidate("NGUYỄN VĂN AN", FieldSource.QR, 1.0),
                    Candidate("NGUYỄN VĂN AN", FieldSource.MRZ, 1.0),
                    Candidate("NGUYỄN VĂN AN", FieldSource.OCR, 1.0),
                ]
            }
        )
        assert result[FieldKey.FULL_NAME].confidence <= 1.0


class TestRule4SourceConflict:
    def test_two_confident_sources_disagreeing_are_flagged_and_devalued(self) -> None:
        result = fuse(
            {
                FieldKey.DATE_OF_BIRTH: [
                    Candidate("1990-05-14", FieldSource.QR, 0.95),
                    Candidate("1990-05-15", FieldSource.MRZ, 0.98),
                ]
            }
        )
        fused = result[FieldKey.DATE_OF_BIRTH]
        assert FLAG_SOURCE_CONFLICT in fused.flags
        assert fused.value == "1990-05-14"  # QR outranks MRZ
        assert fused.confidence == CONTRADICTED_CONFIDENCE
        assert fused.needs_review is True

    def test_two_unsure_sources_disagreeing_are_not_a_conflict(self) -> None:
        """Ordinary noise. The winner's own low score already sends it to review."""
        result = fuse(
            {
                FieldKey.DATE_OF_BIRTH: [
                    Candidate("1990-05-14", FieldSource.QR, 0.80),
                    Candidate("1990-05-15", FieldSource.MRZ, 0.79),
                ]
            }
        )
        assert FLAG_SOURCE_CONFLICT not in result[FieldKey.DATE_OF_BIRTH].flags
        assert result[FieldKey.DATE_OF_BIRTH].needs_review is True

    def test_agreement_is_never_a_conflict(self) -> None:
        result = fuse(
            {
                FieldKey.DATE_OF_BIRTH: [
                    Candidate("1990-05-14", FieldSource.QR, 0.98),
                    Candidate("1990-05-14", FieldSource.MRZ, 0.98),
                ]
            }
        )
        assert FLAG_SOURCE_CONFLICT not in result[FieldKey.DATE_OF_BIRTH].flags


class TestRule5CardMismatch:
    def test_qr_mrz_id_disagreement_is_flagged(self) -> None:
        result = fuse(
            {
                FieldKey.ID_NUMBER: [
                    Candidate(VALID_ID, FieldSource.QR, 0.95),
                    Candidate("001199099999", FieldSource.MRZ, 0.95),
                ]
            }
        )
        assert FLAG_CARD_MISMATCH in result[FieldKey.ID_NUMBER].flags
        assert result[FieldKey.ID_NUMBER].needs_review is True

    def test_qr_mrz_agreement_is_not_flagged(self) -> None:
        result = fuse(
            {
                FieldKey.ID_NUMBER: [
                    Candidate(VALID_ID, FieldSource.QR, 0.95),
                    Candidate(VALID_ID, FieldSource.MRZ, 0.95),
                ]
            }
        )
        assert FLAG_CARD_MISMATCH not in result[FieldKey.ID_NUMBER].flags

    def test_mismatch_only_applies_to_the_id_number(self) -> None:
        result = fuse(
            {
                FieldKey.FULL_NAME: [
                    Candidate("A VAN", FieldSource.QR, 0.95),
                    Candidate("B VAN", FieldSource.MRZ, 0.95),
                ]
            }
        )
        assert FLAG_CARD_MISMATCH not in result[FieldKey.FULL_NAME].flags

    def test_ocr_disagreeing_with_qr_is_not_a_card_mismatch(self) -> None:
        """Two images not being the same card is a QR-vs-MRZ statement only."""
        result = fuse(
            {
                FieldKey.ID_NUMBER: [
                    Candidate(VALID_ID, FieldSource.QR, 1.0),
                    Candidate("001199099999", FieldSource.OCR, 0.99),
                ]
            }
        )
        assert FLAG_CARD_MISMATCH not in result[FieldKey.ID_NUMBER].flags


class TestRule6IdConsistency:
    def test_a_consistent_id_and_birth_date_raise_nothing(self) -> None:
        result = fuse(
            {
                FieldKey.ID_NUMBER: [Candidate(VALID_ID, FieldSource.QR, 1.0)],
                FieldKey.DATE_OF_BIRTH: [Candidate(MATCHING_BIRTH_DATE, FieldSource.QR, 1.0)],
            }
        )
        assert result[FieldKey.ID_NUMBER].flags == ()
        assert result[FieldKey.ID_NUMBER].confidence == 1.0

    def test_birth_year_contradicting_the_id_is_flagged(self) -> None:
        """⭐ The check `^\\d{12}$` can never make: digits 5–6 encode the birth year."""
        result = fuse(
            {
                FieldKey.ID_NUMBER: [Candidate(VALID_ID, FieldSource.QR, 1.0)],
                FieldKey.DATE_OF_BIRTH: [Candidate("1987-03-13", FieldSource.QR, 1.0)],
            }
        )
        assert FLAG_ID_INCONSISTENT in result[FieldKey.ID_NUMBER].flags
        assert result[FieldKey.ID_NUMBER].confidence == CONTRADICTED_CONFIDENCE

    def test_century_digit_contradicting_the_birth_year_is_flagged(self) -> None:
        # 4th digit 1 ⇒ born in the 1900s, but the date says 2099 (same `99`).
        result = fuse(
            {
                FieldKey.ID_NUMBER: [Candidate(VALID_ID, FieldSource.QR, 1.0)],
                FieldKey.DATE_OF_BIRTH: [Candidate("2099-05-14", FieldSource.QR, 1.0)],
            }
        )
        assert FLAG_ID_INCONSISTENT in result[FieldKey.ID_NUMBER].flags

    def test_unknown_province_is_flagged_when_the_directory_is_available(self) -> None:
        context = FusionContext(known_province_codes=frozenset({"001", "079"}))
        result = fuse({FieldKey.ID_NUMBER: [Candidate("999199012345", FieldSource.QR, 1.0)]}, context)
        assert FLAG_ID_INCONSISTENT in result[FieldKey.ID_NUMBER].flags

    def test_known_province_is_accepted(self) -> None:
        context = FusionContext(known_province_codes=frozenset({"001"}))
        result = fuse({FieldKey.ID_NUMBER: [Candidate(VALID_ID, FieldSource.QR, 1.0)]}, context)
        assert result[FieldKey.ID_NUMBER].flags == ()

    def test_province_check_is_skipped_without_a_directory(self) -> None:
        result = fuse({FieldKey.ID_NUMBER: [Candidate("999199012345", FieldSource.QR, 1.0)]})
        assert FLAG_ID_INCONSISTENT not in result[FieldKey.ID_NUMBER].flags

    def test_no_birth_date_means_no_verdict(self) -> None:
        result = fuse({FieldKey.ID_NUMBER: [Candidate(VALID_ID, FieldSource.QR, 1.0)]})
        assert result[FieldKey.ID_NUMBER].flags == ()


class TestRule8NeedsReview:
    def test_below_threshold_flagged(self) -> None:
        result = fuse(
            {FieldKey.FULL_NAME: [Candidate("AN VAN", FieldSource.OCR, 0.5)]},
            FusionContext(review_threshold=0.85),
        )
        assert result[FieldKey.FULL_NAME].needs_review is True

    def test_above_threshold_not_flagged(self) -> None:
        result = fuse(
            {FieldKey.FULL_NAME: [Candidate("AN VAN", FieldSource.QR, 0.99)]},
            FusionContext(review_threshold=0.85),
        )
        assert result[FieldKey.FULL_NAME].needs_review is False

    def test_threshold_is_configurable(self) -> None:
        candidates = {FieldKey.FULL_NAME: [Candidate("AN VAN", FieldSource.QR, 0.70)]}
        assert fuse(candidates, FusionContext(review_threshold=0.60))[
            FieldKey.FULL_NAME
        ].needs_review is False


@given(
    st.lists(
        st.builds(
            Candidate,
            value=st.one_of(st.none(), st.text(max_size=20)),
            source=st.sampled_from(list(FieldSource)),
            confidence=st.floats(min_value=-2.0, max_value=2.0, allow_nan=False),
        ),
        max_size=5,
    ),
    st.sampled_from(_ALL_KEYS),
)
@settings(max_examples=200, deadline=None)
def test_property_confidence_always_in_bounds(candidates: list[Candidate], key: FieldKey) -> None:
    """Property #6 (§8.11): FusedField.confidence ∈ [0, 1] for any candidate combination."""
    result = FieldFusionService().fuse({key: candidates}, FusionContext())
    for fused in result.values():
        assert 0.0 <= fused.confidence <= 1.0
        if fused.value is None:
            assert fused.confidence == 0.0
            assert fused.source == FieldSource.NONE
