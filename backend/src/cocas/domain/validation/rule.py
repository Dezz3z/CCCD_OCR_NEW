"""The shape of a validation rule, and what it is given to decide with (§12.7).

⭐ A rule is a *value*, not a method on the engine. That is what makes "adding
a rule = adding an object to the registry, never editing the engine" true
rather than aspirational (§12.7 "Mở rộng").
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Generic, Protocol, TypeVar

from cocas.domain.validation.report import ValidationIssue

T_contra = TypeVar("T_contra", contravariant=True)


class RuleSetKey(str, Enum):
    """The four rule sets of §12.7 — 56 rules across the system."""

    OCR_RESULT = "OCR_RESULT"
    """23 rules (§8.4) — delivered with P2 week 4."""

    CUSTOMER_FORM = "CUSTOMER_FORM"
    """15 rules (§8.5) — P3, when the form and its repositories exist."""

    CONTRACT_GENERATION = "CONTRACT_GENERATION"
    """10 rules (§8.6) — P3."""

    TEMPLATE_REGISTRATION = "TEMPLATE_REGISTRATION"
    """8 rules (§8.7) — P3."""


@dataclass(frozen=True, slots=True)
class RuleContext:
    """Everything a rule may need beyond the target itself.

    ⭐ `today` is passed in, never read from the clock: a rule that calls
    `date.today()` is a rule whose tests pass in June and fail in July, and
    "the card expires in 89 days" has to be reproducible.

    ⭐ Rules that need the database receive a **repository** here (§12.7), never
    a session — the OCR rule set needs none, so the only lookup table it takes
    is `known_province_codes`, loaded once by the caller.
    """

    today: date
    review_threshold: float = 0.85
    known_province_codes: frozenset[str] = field(default_factory=frozenset)


class Rule(Protocol[T_contra]):
    """One named check over one target type."""

    @property
    def code(self) -> str:
        """The `V-*-NNN` identifier from §8.4–§8.7."""
        ...

    def check(self, target: T_contra, context: RuleContext) -> Sequence[ValidationIssue]:
        """Return every issue this rule finds — empty when it is satisfied."""
        ...


T = TypeVar("T")
CheckFn = Callable[[T, RuleContext], Sequence[ValidationIssue]]


@dataclass(frozen=True, slots=True)
class FunctionRule(Generic[T]):
    """Adapts a plain function to `Rule`, so a rule can be written as a function.

    23 classes whose only state is a code string would be 23 files of ceremony
    (P-10). The registry still holds objects, and the engine still knows nothing
    about any particular rule.
    """

    code: str
    _check: CheckFn[T]

    def check(self, target: T, context: RuleContext) -> Sequence[ValidationIssue]:
        return self._check(target, context)
