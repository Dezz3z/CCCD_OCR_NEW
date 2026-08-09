"""Tests for ConfidenceScore."""
import pytest
from hypothesis import given
from hypothesis import strategies as st

from cocas.domain.exceptions import ValidationError
from cocas.domain.value_objects.confidence_score import ConfidenceScore


class TestValid:
    def test_zero(self) -> None:
        assert ConfidenceScore(0.0).value == 0.0

    def test_one(self) -> None:
        assert ConfidenceScore(1.0).value == 1.0

    def test_mid_value(self) -> None:
        ConfidenceScore(0.87)

    def test_factory_zero(self) -> None:
        assert ConfidenceScore.zero().value == 0.0

    def test_factory_full(self) -> None:
        assert ConfidenceScore.full().value == 1.0


class TestInvalid:
    def test_negative(self) -> None:
        with pytest.raises(ValidationError):
            ConfidenceScore(-0.01)

    def test_above_one(self) -> None:
        with pytest.raises(ValidationError):
            ConfidenceScore(1.01)


class TestBehavior:
    def test_below_threshold(self) -> None:
        assert ConfidenceScore(0.5).below(0.7) is True

    def test_not_below_threshold(self) -> None:
        assert ConfidenceScore(0.8).below(0.7) is False

    def test_as_percent(self) -> None:
        assert ConfidenceScore(0.876).as_percent() == 88

    def test_ordering(self) -> None:
        assert ConfidenceScore(0.5) < ConfidenceScore(0.8)


@given(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
def test_property_always_in_bounds(value: float) -> None:
    assert 0.0 <= ConfidenceScore(value).value <= 1.0
