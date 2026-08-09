"""StyledValue value object — a primitive text value plus render styling.

⭐ P-04 / pitfall #4: `RenderContextBuilder` (Application) produces
`StyledValue` instances; only `DocxContextAdapter` (Infrastructure) is
allowed to turn them into `docxtpl.RichText`. Domain/Application must never
import `docxtpl` — this VO exists precisely so they don't have to.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StyledValue:
    """A rendered-document text value carrying only primitive style attributes."""

    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: str | None = None
    size: int | None = None
    font: str | None = None

    def __str__(self) -> str:
        return self.text
