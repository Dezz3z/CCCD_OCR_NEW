"""Tests for ContractNumberGenerator."""
from datetime import date

import pytest

from cocas.domain.exceptions import BusinessRuleViolation
from cocas.domain.services.contract_number_generator import ContractNumberGenerator

GEN = ContractNumberGenerator()


class TestGeneration:
    def test_matches_design_doc_example(self) -> None:
        result = GEN.generate("01A-GDN-{yyyy}{MM}-{seq:05d}", date(2026, 8, 9), 42)
        assert result == "01A-GDN-202608-00042"

    def test_second_template_pattern(self) -> None:
        result = GEN.generate("01A-KQ-{yyyy}{MM}-{seq:05d}", date(2026, 8, 9), 42)
        assert result == "01A-KQ-202608-00042"

    def test_different_padding_width(self) -> None:
        result = GEN.generate("X-{seq:03d}", date(2026, 1, 1), 7)
        assert result == "X-007"

    def test_sequence_exceeding_padding_width_not_truncated(self) -> None:
        result = GEN.generate("X-{seq:03d}", date(2026, 1, 1), 12345)
        assert result == "X-12345"

    def test_zero_sequence(self) -> None:
        result = GEN.generate("X-{seq:05d}", date(2026, 1, 1), 0)
        assert result == "X-00000"

    def test_single_digit_month_padded(self) -> None:
        result = GEN.generate("{yyyy}{MM}", date(2026, 3, 1), 1)
        assert result == "202603"


class TestErrors:
    def test_empty_pattern_rejected(self) -> None:
        with pytest.raises(BusinessRuleViolation) as exc_info:
            GEN.generate("", date(2026, 1, 1), 1)
        assert exc_info.value.code == "EMPTY_CONTRACT_NO_PATTERN"

    def test_negative_sequence_rejected(self) -> None:
        with pytest.raises(BusinessRuleViolation) as exc_info:
            GEN.generate("X-{seq:03d}", date(2026, 1, 1), -1)
        assert exc_info.value.code == "NEGATIVE_CONTRACT_SEQUENCE"

    def test_unsupported_token_rejected(self) -> None:
        with pytest.raises(BusinessRuleViolation) as exc_info:
            GEN.generate("X-{dd}-{seq:03d}", date(2026, 1, 1), 1)
        assert exc_info.value.code == "UNSUPPORTED_CONTRACT_NO_TOKEN"
