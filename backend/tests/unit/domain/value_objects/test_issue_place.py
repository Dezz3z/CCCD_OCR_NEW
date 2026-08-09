"""Tests for IssuePlace (§8.3.9)."""
import pytest

from cocas.domain.exceptions import ValidationError
from cocas.domain.value_objects.issue_place import (
    BO_CONG_AN,
    CUC_CANH_SAT_QLHC_TTXH,
    IssuePlace,
)


class TestValid:
    def test_bo_cong_an(self) -> None:
        assert IssuePlace(BO_CONG_AN).value == BO_CONG_AN

    def test_cuc_canh_sat(self) -> None:
        assert IssuePlace(CUC_CANH_SAT_QLHC_TTXH).value == CUC_CANH_SAT_QLHC_TTXH

    def test_from_exact_text_normalizes_case(self) -> None:
        assert IssuePlace.from_exact_text("bộ công an").value == BO_CONG_AN

    def test_from_exact_text_collapses_whitespace(self) -> None:
        assert IssuePlace.from_exact_text("  BỘ   CÔNG   AN  ").value == BO_CONG_AN


class TestInvalid:
    def test_unrecognized_value(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            IssuePlace("XYZ")
        assert exc_info.value.code == "ISSUE_PLACE_UNRECOGNIZED"

    def test_empty(self) -> None:
        with pytest.raises(ValidationError):
            IssuePlace("")

    def test_partial_match_not_accepted(self) -> None:
        with pytest.raises(ValidationError):
            IssuePlace("CÔNG AN")

    def test_alias_text_not_directly_accepted(self) -> None:
        # Alias resolution (tier 2) is IssuePlaceNormalizer's job, not this VO's.
        with pytest.raises(ValidationError):
            IssuePlace.from_exact_text("CUC CS QLHC VE TTXH")
