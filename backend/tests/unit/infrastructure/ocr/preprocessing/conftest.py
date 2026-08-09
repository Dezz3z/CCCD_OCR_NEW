"""Synthetic card images — enough structure for the transforms to have something real to do.

Deliberately not photographs: these fixtures make the geometry (card outline,
left-hand block, MRZ band) exact, so a failing assertion points at the
transform rather than at an unlucky sample.
"""
from __future__ import annotations

import cv2
import numpy as np
import pytest

CARD_WIDTH = 1012
CARD_HEIGHT = 638


def draw_card(width: int = CARD_WIDTH, height: int = CARD_HEIGHT, *, with_mrz: bool = True):
    """An upright card: dark block left, text lines right, MRZ band along the bottom."""
    card = np.full((height, width, 3), 220, np.uint8)
    cv2.rectangle(card, (int(width * 0.04), int(height * 0.22)),
                  (int(width * 0.30), int(height * 0.62)), (70, 90, 120), -1)
    for index in range(6):
        top = int(height * (0.20 + index * 0.09))
        cv2.rectangle(card, (int(width * 0.36), top),
                      (int(width * (0.55 + 0.05 * (index % 3))), top + 14), (30, 30, 30), -1)
    if with_mrz:
        # A real TD1 block: 3 full-width lines ~0.08 apart, each a run of glyphs.
        glyph_pitch = width * 0.94 / 30
        for line in range(3):
            top = int(height * (0.70 + line * 0.08))
            bottom = top + int(height * 0.025)
            for glyph in range(30):
                left = int(width * 0.03 + glyph * glyph_pitch)
                cv2.rectangle(card, (left, top),
                              (left + int(glyph_pitch * 0.6), bottom), (20, 20, 20), -1)
    return card


def place_on_background(card, canvas_width: int = 1400, canvas_height: int = 1000):
    """Put the card on a contrasting background so contour detection has an outline."""
    canvas = np.full((canvas_height, canvas_width, 3), 30, np.uint8)
    offset_y = (canvas_height - card.shape[0]) // 2
    offset_x = (canvas_width - card.shape[1]) // 2
    canvas[offset_y:offset_y + card.shape[0], offset_x:offset_x + card.shape[1]] = card
    return canvas


def encode(image) -> bytes:
    ok, buffer = cv2.imencode(".png", image)
    assert ok
    return buffer.tobytes()


@pytest.fixture
def card_image():
    return draw_card()


@pytest.fixture
def card_on_background(card_image):
    return place_on_background(card_image)


@pytest.fixture
def card_bytes(card_on_background) -> bytes:
    return encode(card_on_background)
