"""Tests for ValidationEngine and ValidationReport (§12.7, §8.2)."""
from __future__ import annotations

from collections.abc import Sequence

import pytest

from cocas.domain.exceptions import ValidationError
from cocas.domain.validation import (
    FunctionRule,
    OcrValidationTarget,
    RuleContext,
    RuleSetKey,
    Severity,
    ValidationEngine,
    ValidationIssue,
    ValidationReport,
)
from tests.unit.domain.validation.conftest import context, target


def issue(code: str, severity: Severity) -> ValidationIssue:
    return ValidationIssue(code=code, severity=severity, message_vi="…", field="x")


class TestRegistry:
    def test_the_ocr_set_holds_exactly_the_23_documented_rules(self) -> None:
        """⭐ §8.4 says 23; a rule quietly dropped from the tuple would not show up
        in any other test, because every other test asks about one rule it names."""
        registered = ValidationEngine().rules_in(RuleSetKey.OCR_RESULT)
        assert registered == tuple(f"V-OCR-{n:03d}" for n in range(1, 24))

    def test_the_contract_set_holds_exactly_the_10_documented_rules(self) -> None:
        """§8.6 — filled in by P3 module 6; same guard as the OCR set above."""
        registered = ValidationEngine().rules_in(RuleSetKey.CONTRACT_GENERATION)
        assert registered == tuple(f"V-CTR-{n:03d}" for n in range(1, 11))

    def test_the_remaining_p3_sets_are_registered_but_empty(self) -> None:
        engine = ValidationEngine()
        for key in (RuleSetKey.CUSTOMER_FORM, RuleSetKey.TEMPLATE_REGISTRATION):
            assert engine.rules_in(key) == ()

    def test_an_empty_set_returns_a_valid_report_rather_than_raising(self) -> None:
        report = ValidationEngine().validate(
            object(), RuleSetKey.CUSTOMER_FORM, context()
        )
        assert report.is_valid is True

    def test_an_unregistered_set_raises(self) -> None:
        engine = ValidationEngine(registry={})
        with pytest.raises(ValidationError):
            engine.validate(target(), RuleSetKey.OCR_RESULT, context())


class TestExtensibility:
    def test_a_new_rule_is_added_to_the_registry_not_to_the_engine(self) -> None:
        """⭐ §12.7's extension promise, exercised rather than asserted in prose."""

        def always_complains(
            _target: OcrValidationTarget, _context: RuleContext
        ) -> Sequence[ValidationIssue]:
            return [issue("V-TEST-001", Severity.ERROR)]

        engine = ValidationEngine(
            registry={RuleSetKey.OCR_RESULT: (FunctionRule("V-TEST-001", always_complains),)}
        )
        report = engine.validate(target(), RuleSetKey.OCR_RESULT, context())
        assert report.codes() == ("V-TEST-001",)

    def test_every_rule_runs_even_after_one_produces_an_error(self) -> None:
        def complain(code: str):  # type: ignore[no-untyped-def]
            def _check(
                _target: OcrValidationTarget, _context: RuleContext
            ) -> Sequence[ValidationIssue]:
                return [issue(code, Severity.ERROR)]

            return _check

        engine = ValidationEngine(
            registry={
                RuleSetKey.OCR_RESULT: (
                    FunctionRule("A", complain("A")),
                    FunctionRule("B", complain("B")),
                    FunctionRule("C", complain("C")),
                )
            }
        )
        assert engine.validate(target(), RuleSetKey.OCR_RESULT, context()).codes() == (
            "A",
            "B",
            "C",
        )


class TestReport:
    def test_is_valid_tracks_errors_only(self) -> None:
        """⭐ The invariant of §12.7: `is_valid == (len(errors) == 0)`."""
        report = ValidationReport(
            issues=(issue("W", Severity.WARNING), issue("I", Severity.INFO))
        )
        assert report.is_valid is True
        assert len(report.warnings) == 1
        assert len(report.infos) == 1

    def test_one_error_invalidates_the_report(self) -> None:
        report = ValidationReport(issues=(issue("E", Severity.ERROR),))
        assert report.is_valid is False
        assert report.errors[0].code == "E"

    def test_an_empty_report_is_valid(self) -> None:
        assert ValidationReport().is_valid is True

    def test_issues_keep_the_order_the_rules_ran_in(self) -> None:
        report = ValidationReport(
            issues=(issue("B", Severity.WARNING), issue("A", Severity.ERROR))
        )
        assert report.codes() == ("B", "A")
