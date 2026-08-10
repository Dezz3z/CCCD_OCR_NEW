"""The engine-backed half of §7.4.1 transform 4 — is this card upside down?

⭐ **The design's second signal does not work, and this is the measurement that
says so.** §7.4.1 proposes voting on "how many text regions were read at 0° vs
180°". Run over 18 real fronts, upright against the same card rotated:

| | Upright | Rotated 180° |
|---|---|---|
| Regions read | 17.7 | 15.8 |
| Mean confidence | 0.911 | 0.904 |
| Text lines identical to upright | — | 84 of 318 |

PaddleOCR's per-line angle classifier flips each detected line on its own, so
an inverted card still yields a full page of confident text — 74% of it simply
wrong. Region count and confidence cannot separate those two states. What can
is *what the text says*: a card read the right way up contains the phrases
every CCCD prints.

⭐ Costs one small recognition pass on the common (upright) path. The second
pass happens only when the first finds no card text at all, which is exactly
the case worth spending on.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, cast

import cv2
from loguru import logger

from cocas.domain.ports.ocr import ImageData, RelativeBox

from ..preprocessing.image_data import BgrArray, NumpyImageData
from ..text_matching import BOILERPLATE_THRESHOLD, CARD_TOP_FINGERPRINT, matches_any

if TYPE_CHECKING:
    from cocas.domain.ports.ocr import IRegionRecognizer

# Both sides print identifying text in the top third — the same strip the side
# classifier reads, and small enough that two passes stay affordable.
_TITLE_BAND = RelativeBox(x=0.0, y=0.0, w=1.0, h=0.32)


class PaddleOrientationOracle:
    """Decide orientation by whether the card's own printed phrases appear."""

    def __init__(self, recognizer: IRegionRecognizer) -> None:
        self._recognizer = recognizer

    def is_upside_down(self, image: ImageData) -> bool | None:
        """True if upside down, False if upright, None if neither view is legible.

        ⭐ Abstains rather than guessing. Rotating a correctly-oriented card is
        far more damaging than leaving an inverted one for the channels, which
        is the same rule the MRZ signal follows (§7.4.1).
        """
        if self._prints_card_text(image):
            return False

        array = _array_of(image)
        rotated = NumpyImageData(cast(BgrArray, cv2.rotate(array, cv2.ROTATE_180)))
        if self._prints_card_text(rotated):
            logger.info("Card recognized only when rotated 180°; correcting orientation")
            return True

        return None

    def _prints_card_text(self, image: ImageData) -> bool:
        """Whether the top strip reads as text a CCCD actually prints."""
        try:
            region = self._recognizer.recognize_region(image, _TITLE_BAND, None)
        except Exception:
            logger.opt(exception=True).debug("Orientation probe failed to recognize")
            return False
        if region is None:
            return False
        return any(
            matches_any(line, CARD_TOP_FINGERPRINT, BOILERPLATE_THRESHOLD)
            for line in region.text.splitlines()
        )


def _array_of(image: ImageData) -> BgrArray:
    return cast(NumpyImageData, image).array
