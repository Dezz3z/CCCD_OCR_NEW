"""ValidationEngine — runs a rule set and reports everything it found (§12.7).

⭐ The engine knows **no rules**. It looks a set up in a registry, runs every
member, and concatenates the findings. That is the whole implementation, and
it is why §12.7 can promise that adding a rule never touches this file.

⭐ **It never stops at the first error.** A user correcting one field at a time
because the engine gave up after the first problem is the failure mode this
postcondition exists to prevent.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from cocas.domain.exceptions import ValidationError
from cocas.domain.validation.ocr_rules import OCR_RESULT_RULES
from cocas.domain.validation.report import ValidationIssue, ValidationReport
from cocas.domain.validation.rule import Rule, RuleContext, RuleSetKey

# ⚠️ The three P3 sets are registered empty rather than omitted. An empty set
# returns a valid report; a missing key raises. Those are different answers to
# "is this contract ready to generate?", and the wrong one would let P3 ship a
# use case that silently validates nothing.
DEFAULT_REGISTRY: Mapping[RuleSetKey, tuple[Rule[Any], ...]] = {
    RuleSetKey.OCR_RESULT: OCR_RESULT_RULES,
    RuleSetKey.CUSTOMER_FORM: (),
    RuleSetKey.CONTRACT_GENERATION: (),
    RuleSetKey.TEMPLATE_REGISTRATION: (),
}


class ValidationEngine:
    """Domain Service — see module docstring."""

    def __init__(self, registry: Mapping[RuleSetKey, Sequence[Rule[Any]]] | None = None) -> None:
        self._registry: Mapping[RuleSetKey, Sequence[Rule[Any]]] = (
            DEFAULT_REGISTRY if registry is None else registry
        )

    def validate(
        self, target: Any, rule_set: RuleSetKey, context: RuleContext
    ) -> ValidationReport:
        """Run every rule in `rule_set` against `target`.

        Raises:
            ValidationError: `rule_set` is not registered (a wiring bug, not
                a data problem — the precondition of §12.7).
        """
        rules = self._registry.get(rule_set)
        if rules is None:
            raise ValidationError(
                f"Không có tập quy tắc '{rule_set.value}'.",
                code="UNKNOWN_RULE_SET",
            )

        issues: list[ValidationIssue] = []
        for rule in rules:
            issues.extend(rule.check(target, context))
        return ValidationReport(issues=tuple(issues))

    def rules_in(self, rule_set: RuleSetKey) -> tuple[str, ...]:
        """The codes registered for a set — used by the "all 23 present" test."""
        return tuple(rule.code for rule in self._registry.get(rule_set, ()))
