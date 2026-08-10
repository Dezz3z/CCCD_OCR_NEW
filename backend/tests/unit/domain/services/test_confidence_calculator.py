"""Tests for ConfidenceCalculator (§03 S10 rule 7) — one score for the whole card."""
import pytest

from cocas.domain.enums.field_key import FieldKey
from cocas.domain.enums.field_source import FieldSource
from cocas.domain.services.confidence_calculator import (
    FIELD_WEIGHTS,
    RETAKE_THRESHOLD,
    ConfidenceCalculator,
)
from cocas.domain.services.field_fusion_service import FusedField


def read(value: str | None, confidence: float) -> FusedField:
    return FusedField(
        value=value,
        confidence=confidence,
        source=FieldSource.QR if value else FieldSource.NONE,
        needs_review=confidence < 0.85,
    )


def all_fields(confidence: float) -> dict[FieldKey, FusedField]:
    return {key: read("x", confidence) for key in FieldKey}


class TestWeights:
    def test_weights_sum_to_one(self) -> None:
        assert sum(FIELD_WEIGHTS.values()) == pytest.approx(1.0)

    def test_every_field_has_a_weight(self) -> None:
        assert set(FIELD_WEIGHTS) == set(FieldKey)

    def test_id_number_is_worth_three_issue_places(self) -> None:
        assert FIELD_WEIGHTS[FieldKey.ID_NUMBER] == pytest.approx(
            3 * FIELD_WEIGHTS[FieldKey.ISSUE_PLACE]
        )


class TestOverall:
    def test_a_perfect_read_scores_one(self) -> None:
        assert ConfidenceCalculator().overall(all_fields(1.0)) == 1.0

    def test_nothing_read_scores_zero(self) -> None:
        assert ConfidenceCalculator().overall({}) == 0.0

    def test_the_score_is_weighted_not_averaged(self) -> None:
        fields = all_fields(1.0)
        fields[FieldKey.ID_NUMBER] = read(None, 0.0)
        # Losing the id number costs 0.30, not one sixth.
        assert ConfidenceCalculator().overall(fields) == pytest.approx(0.70)

    def test_a_missing_field_counts_as_zero_not_as_absent(self) -> None:
        """⭐ Otherwise one perfectly-read field out of six scores 1.00."""
        only_id = {FieldKey.ID_NUMBER: read("001199012345", 1.0)}
        assert ConfidenceCalculator().overall(only_id) == pytest.approx(
            FIELD_WEIGHTS[FieldKey.ID_NUMBER]
        )

    def test_a_value_with_low_confidence_still_contributes(self) -> None:
        assert ConfidenceCalculator().overall(all_fields(0.5)) == pytest.approx(0.5)


class TestRetake:
    def test_a_poor_read_asks_for_a_new_photo(self) -> None:
        assert ConfidenceCalculator().needs_retake(all_fields(0.2)) is True

    def test_a_decent_read_does_not(self) -> None:
        assert ConfidenceCalculator().needs_retake(all_fields(0.8)) is False

    def test_the_threshold_is_the_documented_alt_03_value(self) -> None:
        assert RETAKE_THRESHOLD == 0.40
