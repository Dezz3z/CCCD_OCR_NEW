"""What a validation run produces (§8.2, §12.7).

Three severities, because "invalid" is not one thing. §8.2 ties each to a
concrete UI behaviour, and the whole point of keeping them apart is that a
🟡 must never silently become a 🔴: a card that expired last month is
suspicious, not unusable, and blocking it would leave the user with no way
forward at all (P-08).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    """§8.2 — how hard an issue pushes back."""

    ERROR = "ERROR"
    """🔴 Invariant violated. Blocks: the wizard's "Tiếp tục" is disabled."""

    WARNING = "WARNING"
    """🟡 Suspicious but possibly right. Soft block: the user ticks to confirm."""

    INFO = "INFO"
    """🔵 Context. Never blocks."""


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One finding. `field` is `None` for issues about the submission as a whole."""

    code: str
    severity: Severity
    message_vi: str
    field: str | None = None
    hint: str | None = None


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Everything wrong with one target, in one pass.

    ⭐ Invariant (§12.7): `is_valid == (len(errors) == 0)`. Warnings and infos
    never make a report invalid — they are shown, not enforced.
    """

    issues: tuple[ValidationIssue, ...] = ()

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return self._by(Severity.ERROR)

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return self._by(Severity.WARNING)

    @property
    def infos(self) -> tuple[ValidationIssue, ...]:
        return self._by(Severity.INFO)

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def codes(self) -> tuple[str, ...]:
        """Every code raised, in the order the rules ran — handy in tests and logs."""
        return tuple(issue.code for issue in self.issues)

    def _by(self, severity: Severity) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity is severity)
