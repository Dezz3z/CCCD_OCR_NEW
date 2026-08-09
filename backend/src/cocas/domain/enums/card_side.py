"""CCCD card side (§4.3.3 `CardSide`, `card_image.side_hint`/`side_resolved`)."""
from enum import Enum


class CardSide(str, Enum):
    """Which side of the ID card an image shows."""

    FRONT = "FRONT"
    BACK = "BACK"
    UNKNOWN = "UNKNOWN"
