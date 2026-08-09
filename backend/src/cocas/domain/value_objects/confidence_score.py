"""ConfidenceScore value object — a probability-like score in [0, 1]."""
from __future__ import annotations

from dataclasses import dataclass

from cocas.domain.exceptions import ValidationError


@dataclass(frozen=True, slots=True, order=True)
class ConfidenceScore:
    """A confidence value, always within the closed interval [0, 1]."""

    value: float

    def __post_init__(self) -> None:
        if not (0.0 <= self.value <= 1.0):
            raise ValidationError(
                f"Độ tin cậy phải nằm trong khoảng 0 đến 1. Hiện có {self.value}.",
                code="INVALID_CONFIDENCE_SCORE",
                field="confidence",
            )

    @classmethod
    def zero(cls) -> ConfidenceScore:
        return cls(0.0)

    @classmethod
    def full(cls) -> ConfidenceScore:
        return cls(1.0)

    def below(self, threshold: float) -> bool:
        return self.value < threshold

    def as_percent(self) -> int:
        return round(self.value * 100)

    def __str__(self) -> str:
        return f"{self.value:.4f}"
