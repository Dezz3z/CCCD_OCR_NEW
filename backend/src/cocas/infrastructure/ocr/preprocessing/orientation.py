"""The seam that lets preprocessing ask an OCR engine which way up a card is.

⭐ §7.4.1 transform 4 wants three voting signals, and two of them need an
engine. Preprocessing must not depend on one — it has to keep working, and
keep being testable, with no models installed at all. So it depends on this
one-method protocol instead, and the Composition Root supplies an engine-backed
implementation when there is an engine to back it with.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from cocas.domain.ports.ocr import ImageData


@runtime_checkable
class IOrientationOracle(Protocol):
    """A second opinion on whether a rectified card is rotated 180°."""

    def is_upside_down(self, image: ImageData) -> bool | None:
        """True if upside down, False if upright, ⭐ None if it cannot tell.

        Abstaining must stay possible: a wrong `False` is indistinguishable
        from "upright" and silently disables every later signal.
        """
        ...
