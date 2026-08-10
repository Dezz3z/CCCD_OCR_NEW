"""`PaddleOrientationOracle` — the engine's vote on §7.4.1 transform 4.

⭐ The design proposed voting on how many text regions were read at 0° vs 180°.
Measured over 18 real fronts that signal does not exist: 17.7 regions upright
against 15.8 flipped, confidence 0.911 against 0.904. PaddleOCR's per-line
angle classifier flips each detected line by itself, so an inverted card still
produces a full page of confident text — 74% of it simply wrong. What separates
the two states is *what the text says*, which is what these tests pin down.
"""
from __future__ import annotations

import numpy as np

from cocas.domain.ports.ocr import TextRegion
from cocas.infrastructure.ocr.engines import PaddleOrientationOracle
from cocas.infrastructure.ocr.preprocessing.image_data import NumpyImageData

FRONT_TOP = "CONG HOAXAHOI CHU NGHIAVIET NAM\nCAN CU'O'C CONG DAN"
BACK_TOP = "Dac diem nhan dang/ Personal identification:"
# What the top band of a flipped front actually returns — the bottom of the
# card, rendered legibly by the per-line angle classifier.
FLIPPED_FRONT_TOP = "co gia nden27/02/2039\nNoithuong tru/Place of residence"


class OrientedRecognizer:
    """Returns one text for the image as given and another once it is rotated.

    Orientation is inferred from a marker pixel, which is how a single stub can
    answer both probes the oracle makes.
    """

    def __init__(self, upright_text: str | None, flipped_text: str | None) -> None:
        self._upright = upright_text
        self._flipped = flipped_text
        self.calls = 0

    def recognize_region(self, image, bbox, charset_hint):
        self.calls += 1
        text = self._upright if image.array[0, 0, 0] == 1 else self._flipped
        return None if text is None else TextRegion(bbox, text, 0.9)


def card(*, upright: bool = True) -> NumpyImageData:
    """An image whose top-left pixel marks which way up it is."""
    array = np.zeros((638, 1012, 3), np.uint8)
    array[0, 0, 0] = 1 if upright else 2
    return NumpyImageData(array)


class TestVerdicts:
    def test_a_card_showing_its_own_title_is_upright(self):
        oracle = PaddleOrientationOracle(OrientedRecognizer(FRONT_TOP, None))
        assert oracle.is_upside_down(card()) is False

    def test_a_back_showing_its_heading_is_upright(self):
        oracle = PaddleOrientationOracle(OrientedRecognizer(BACK_TOP, None))
        assert oracle.is_upside_down(card()) is False

    def test_a_card_legible_only_when_rotated_is_upside_down(self):
        oracle = PaddleOrientationOracle(
            OrientedRecognizer(FLIPPED_FRONT_TOP, FRONT_TOP)
        )
        assert oracle.is_upside_down(card()) is True

    def test_abstains_when_neither_view_shows_card_text(self):
        """⭐ Rotating a correctly-oriented card is worse than leaving an
        inverted one, so silence is the safe answer — and the measured one:
        0 wrong verdicts across 46 cards tested both ways up, 2 abstentions."""
        oracle = PaddleOrientationOracle(OrientedRecognizer("gibberish", "more noise"))
        assert oracle.is_upside_down(card()) is None

    def test_abstains_when_nothing_is_recognized_at_all(self):
        oracle = PaddleOrientationOracle(OrientedRecognizer(None, None))
        assert oracle.is_upside_down(card()) is None


class TestBottomOfCardPhrases:
    """⭐ The fingerprint must be text printed only at the TOP of a card.

    Built from every printed phrase, it called 6 of 46 inverted cards upright:
    `Nơi thường trú` and `Có giá trị đến` sit at the foot of a front, so
    rotating the card moves them straight into the band being searched.
    """

    def test_bottom_of_card_text_does_not_prove_the_card_is_upright(self):
        oracle = PaddleOrientationOracle(
            OrientedRecognizer(FLIPPED_FRONT_TOP, FRONT_TOP)
        )
        assert oracle.is_upside_down(card()) is True


class TestCost:
    """⭐ One recognition pass on the common path, two only when the first
    finds nothing. Each pass costs 41% of a whole-card recognition."""

    def test_an_upright_card_costs_a_single_pass(self):
        recognizer = OrientedRecognizer(FRONT_TOP, None)
        PaddleOrientationOracle(recognizer).is_upside_down(card())
        assert recognizer.calls == 1

    def test_only_an_unreadable_top_band_pays_for_the_second_pass(self):
        recognizer = OrientedRecognizer("gibberish", FRONT_TOP)
        PaddleOrientationOracle(recognizer).is_upside_down(card())
        assert recognizer.calls == 2


class TestResilience:
    def test_a_dying_engine_is_reported_as_no_opinion(self):
        class Exploding:
            def recognize_region(self, image, bbox, charset_hint):
                raise RuntimeError("engine died mid-probe")

        assert PaddleOrientationOracle(Exploding()).is_upside_down(card()) is None
