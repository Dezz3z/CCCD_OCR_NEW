"""`OpenCvPreprocessor` against every clause of the §12.4 spec table."""
from __future__ import annotations

import cv2
import numpy as np
import pytest

from cocas.domain.exceptions import ImageDecodeError, ImageTooSmallError
from cocas.domain.ports.ocr import IImagePreprocessor, PreprocessProfile
from cocas.infrastructure.ocr.preprocessing import MIN_SHORT_EDGE, OpenCvPreprocessor

from .conftest import draw_card, encode


@pytest.fixture
def preprocessor() -> OpenCvPreprocessor:
    return OpenCvPreprocessor()


@pytest.fixture
def profile() -> PreprocessProfile:
    return PreprocessProfile()


def test_satisfies_the_port(preprocessor):
    assert isinstance(preprocessor, IImagePreprocessor)


class TestRejectedInput:
    def test_empty_bytes(self, preprocessor, profile):
        with pytest.raises(ImageDecodeError):
            preprocessor.prepare(b"", None, profile)

    def test_bytes_that_are_not_an_image(self, preprocessor, profile):
        with pytest.raises(ImageDecodeError):
            preprocessor.prepare(b"this is a .docx, not a photo", None, profile)

    def test_truncated_image(self, preprocessor, profile):
        with pytest.raises(ImageDecodeError):
            preprocessor.prepare(encode(draw_card())[:120], None, profile)

    def test_image_below_the_minimum_short_edge(self, preprocessor, profile):
        tiny = encode(draw_card(width=500, height=MIN_SHORT_EDGE - 1))
        with pytest.raises(ImageTooSmallError) as raised:
            preprocessor.prepare(tiny, None, profile)
        assert str(MIN_SHORT_EDGE) in raised.value.message

    def test_error_messages_are_vietnamese_and_carry_a_hint(self, preprocessor, profile):
        with pytest.raises(ImageDecodeError) as raised:
            preprocessor.prepare(b"", None, profile)
        assert "ảnh" in raised.value.message.lower()
        assert raised.value.hint


class TestAcceptedInput:
    def test_v0_matches_the_decoded_source(self, preprocessor, profile, card_bytes,
                                           card_on_background):
        image_set = preprocessor.prepare(card_bytes, None, profile)
        assert (image_set.v0.width, image_set.v0.height) == (
            card_on_background.shape[1],
            card_on_background.shape[0],
        )
        assert np.array_equal(image_set.v0.array, card_on_background)

    def test_greyscale_source_is_decoded_as_three_channel(self, preprocessor, profile):
        grey = cv2.cvtColor(draw_card(), cv2.COLOR_BGR2GRAY)
        image_set = preprocessor.prepare(encode(grey), None, profile)
        assert image_set.v0.array.shape[2] == 3

    def test_decoding_is_the_only_eager_work(self, preprocessor, profile, card_bytes):
        """⭐ `prepare()` must not build a single variant (§7.4.1 lazy strategy)."""
        image_set = preprocessor.prepare(card_bytes, None, profile)
        assert image_set.built_variants() == set()

    def test_jpeg_and_png_are_both_accepted(self, preprocessor, profile, card_on_background):
        for extension in (".jpg", ".png"):
            ok, buffer = cv2.imencode(extension, card_on_background)
            assert ok
            assert preprocessor.prepare(buffer.tobytes(), None, profile).v0.width > 0
