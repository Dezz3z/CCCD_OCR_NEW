"""Tests for FieldFusionService (§12.6)."""
from hypothesis import given, settings
from hypothesis import strategies as st

from cocas.domain.enums.field_key import FieldKey
from cocas.domain.enums.field_source import FieldSource
from cocas.domain.services.field_fusion_service import (
    Candidate,
    FieldFusionService,
    FusionContext,
)

_ALL_KEYS = list(FieldKey)


class TestAllSixKeysPresent:
    def test_empty_input_still_yields_6_keys(self) -> None:
        result = FieldFusionService().fuse({}, FusionContext())
        assert set(result.keys()) == set(_ALL_KEYS)

    def test_partial_input_still_yields_6_keys(self) -> None:
        candidates = {FieldKey.FULL_NAME: [Candidate("NGUYỄN VĂN AN", FieldSource.QR, 1.0)]}
        result = FieldFusionService().fuse(candidates, FusionContext())
        assert set(result.keys()) == set(_ALL_KEYS)


class TestNoneInvariant:
    def test_no_candidates_yields_none_and_zero_confidence(self) -> None:
        result = FieldFusionService().fuse({}, FusionContext())
        fused = result[FieldKey.FULL_NAME]
        assert fused.value is None
        assert fused.confidence == 0.0
        assert fused.source == FieldSource.NONE
        assert fused.needs_review is True

    def test_all_candidates_none_value_yields_none(self) -> None:
        candidates = {FieldKey.FULL_NAME: [Candidate(None, FieldSource.OCR, 0.5)]}
        result = FieldFusionService().fuse(candidates, FusionContext())
        assert result[FieldKey.FULL_NAME].value is None
        assert result[FieldKey.FULL_NAME].source == FieldSource.NONE


class TestSourcePriority:
    def test_qr_wins_over_ocr_when_disagreeing_and_similar_confidence(self) -> None:
        candidates = {
            FieldKey.ID_NUMBER: [
                Candidate("001199012345", FieldSource.QR, 0.95),
                Candidate("001199099999", FieldSource.OCR, 0.90),
            ]
        }
        result = FieldFusionService().fuse(candidates, FusionContext())
        assert result[FieldKey.ID_NUMBER].value == "001199012345"
        assert result[FieldKey.ID_NUMBER].source == FieldSource.QR

    def test_higher_confidence_can_override_lower_priority_source(self) -> None:
        candidates = {
            FieldKey.ISSUE_PLACE: [
                Candidate("BỘ CÔNG AN", FieldSource.QR, 0.50),
                Candidate("BỘ CÔNG AN", FieldSource.OCR, 0.99),
            ]
        }
        # Same value from both — consensus bonus applies to both; QR still wins ties.
        result = FieldFusionService().fuse(candidates, FusionContext())
        assert result[FieldKey.ISSUE_PLACE].value == "BỘ CÔNG AN"


class TestConsensusBonus:
    def test_agreement_across_sources_boosts_confidence(self) -> None:
        candidates = {
            FieldKey.FULL_NAME: [
                Candidate("NGUYỄN VĂN AN", FieldSource.QR, 0.80),
                Candidate("NGUYỄN VĂN AN", FieldSource.MRZ, 0.80),
            ]
        }
        result = FieldFusionService().fuse(candidates, FusionContext())
        assert result[FieldKey.FULL_NAME].confidence > 0.80

    def test_confidence_never_exceeds_one(self) -> None:
        candidates = {
            FieldKey.FULL_NAME: [
                Candidate("NGUYỄN VĂN AN", FieldSource.QR, 1.0),
                Candidate("NGUYỄN VĂN AN", FieldSource.MRZ, 1.0),
                Candidate("NGUYỄN VĂN AN", FieldSource.OCR, 1.0),
            ]
        }
        result = FieldFusionService().fuse(candidates, FusionContext())
        assert result[FieldKey.FULL_NAME].confidence <= 1.0


class TestSourceConflictFlag:
    def test_close_disagreement_flagged(self) -> None:
        candidates = {
            FieldKey.DATE_OF_BIRTH: [
                Candidate("1990-05-14", FieldSource.QR, 0.80),
                Candidate("1990-05-15", FieldSource.MRZ, 0.79),
            ]
        }
        result = FieldFusionService().fuse(candidates, FusionContext())
        assert "SOURCE_CONFLICT" in result[FieldKey.DATE_OF_BIRTH].flags

    def test_agreement_not_flagged(self) -> None:
        candidates = {
            FieldKey.DATE_OF_BIRTH: [
                Candidate("1990-05-14", FieldSource.QR, 0.90),
                Candidate("1990-05-14", FieldSource.MRZ, 0.90),
            ]
        }
        result = FieldFusionService().fuse(candidates, FusionContext())
        assert "SOURCE_CONFLICT" not in result[FieldKey.DATE_OF_BIRTH].flags


class TestCardMismatchFlag:
    def test_qr_mrz_id_number_disagreement_flagged(self) -> None:
        candidates = {
            FieldKey.ID_NUMBER: [
                Candidate("001199012345", FieldSource.QR, 0.95),
                Candidate("001199099999", FieldSource.MRZ, 0.95),
            ]
        }
        result = FieldFusionService().fuse(candidates, FusionContext())
        assert "CARD_MISMATCH" in result[FieldKey.ID_NUMBER].flags
        assert result[FieldKey.ID_NUMBER].needs_review is True

    def test_qr_mrz_agreement_not_flagged(self) -> None:
        candidates = {
            FieldKey.ID_NUMBER: [
                Candidate("001199012345", FieldSource.QR, 0.95),
                Candidate("001199012345", FieldSource.MRZ, 0.95),
            ]
        }
        result = FieldFusionService().fuse(candidates, FusionContext())
        assert "CARD_MISMATCH" not in result[FieldKey.ID_NUMBER].flags

    def test_mismatch_only_applies_to_id_number(self) -> None:
        candidates = {
            FieldKey.FULL_NAME: [
                Candidate("A", FieldSource.QR, 0.95),
                Candidate("B", FieldSource.MRZ, 0.95),
            ]
        }
        result = FieldFusionService().fuse(candidates, FusionContext())
        assert "CARD_MISMATCH" not in result[FieldKey.FULL_NAME].flags


class TestNeedsReview:
    def test_below_threshold_flagged(self) -> None:
        candidates = {FieldKey.FULL_NAME: [Candidate("AN", FieldSource.OCR, 0.5)]}
        result = FieldFusionService().fuse(candidates, FusionContext(review_threshold=0.85))
        assert result[FieldKey.FULL_NAME].needs_review is True

    def test_above_threshold_not_flagged(self) -> None:
        candidates = {FieldKey.FULL_NAME: [Candidate("AN", FieldSource.QR, 0.99)]}
        result = FieldFusionService().fuse(candidates, FusionContext(review_threshold=0.85))
        assert result[FieldKey.FULL_NAME].needs_review is False


@given(
    st.lists(
        st.builds(
            Candidate,
            value=st.one_of(st.none(), st.text(max_size=20)),
            source=st.sampled_from(list(FieldSource)),
            confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        ),
        max_size=5,
    )
)
@settings(max_examples=100, deadline=None)
def test_property_confidence_always_in_bounds(candidates: list[Candidate]) -> None:
    """Property #6 (§8.11): FusedField.confidence ∈ [0, 1] for any candidate combination."""
    result = FieldFusionService().fuse({FieldKey.FULL_NAME: candidates}, FusionContext())
    fused = result[FieldKey.FULL_NAME]
    assert 0.0 <= fused.confidence <= 1.0
    if fused.value is None:
        assert fused.confidence == 0.0
        assert fused.source == FieldSource.NONE
