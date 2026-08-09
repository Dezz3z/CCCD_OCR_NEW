"""Fixtures for the QR and MRZ channel tests.

QR images are *generated*, not sampled: a synthetic payload keeps real citizen
data out of the repository while still exercising the real decoder end to end.
"""
from __future__ import annotations

import cv2
import numpy as np
import pytest
import zxingcpp

from cocas.domain.ports.ocr import ImageQuality
from cocas.infrastructure.ocr.preprocessing.image_data import NumpyImageData

SAMPLE_PAYLOAD = (
    "048179002546|179002546|VO HUYNH NGAN GIAO|27021979|Nu|"
    "37 Truong Han Sieu, Phuoc Long, Nha Trang|08112022"
)

REAL_MRZ_LINES = [
    "IDVNM1790025462048179002546<<2",
    "7902273F3902275VNM<<<<<<<<<<<2",
    "VO<<HUYNH<NGAN<GIAO<<<<<<<<<<<",
]

QUIET_ZONE = 16
MODULE_SCALE = 8


def render_qr(payload: str) -> np.ndarray:
    """A BGR image holding `payload`, scaled and quiet-zoned like a printed code."""
    barcode = zxingcpp.create_barcode(payload, zxingcpp.BarcodeFormat.QRCode)
    matrix = np.array(zxingcpp.write_barcode_to_image(barcode))
    scaled = np.kron(matrix, np.ones((MODULE_SCALE, MODULE_SCALE), dtype=matrix.dtype))
    padded = np.pad(scaled, QUIET_ZONE, mode="constant", constant_values=255)
    return cv2.cvtColor(padded, cv2.COLOR_GRAY2BGR)


def card_with_qr(payload: str, width: int = 1012, height: int = 638) -> np.ndarray:
    """A card-shaped image carrying the QR in the top-right corner, as printed."""
    card = np.full((height, width, 3), 220, np.uint8)
    qr = render_qr(payload)
    qr_size = int(height * 0.30)
    qr = cv2.resize(qr, (qr_size, qr_size), interpolation=cv2.INTER_NEAREST)
    top, left = int(height * 0.05), width - qr_size - int(width * 0.04)
    card[top : top + qr_size, left : left + qr_size] = qr
    return card


class StubImageSet:
    """A `PreprocessedImageSet` whose variants are plain arrays under our control.

    Records which variants were touched so a test can assert the decoder stops
    at its first success instead of building everything.
    """

    def __init__(self, image: np.ndarray, *, warp_succeeded: bool = True) -> None:
        self._image = NumpyImageData(image)
        self._warp_succeeded = warp_succeeded
        self.accessed: list[str] = []

    def _touch(self, name: str) -> NumpyImageData:
        self.accessed.append(name)
        return self._image

    @property
    def v0(self) -> NumpyImageData:
        return self._touch("v0")

    @property
    def v1(self) -> NumpyImageData:
        return self._touch("v1")

    @property
    def v2(self) -> NumpyImageData:
        return self._touch("v2")

    @property
    def v3(self) -> NumpyImageData:
        return self._touch("v3")

    @property
    def v4(self) -> NumpyImageData:
        return self._touch("v4")

    @property
    def transform_matrix(self) -> list[list[float]] | None:
        return None

    @property
    def warp_succeeded(self) -> bool:
        return self._warp_succeeded

    @property
    def quality(self) -> ImageQuality:
        return ImageQuality(score=0.9)


@pytest.fixture
def qr_card_set() -> StubImageSet:
    return StubImageSet(card_with_qr(SAMPLE_PAYLOAD))


@pytest.fixture
def blank_set() -> StubImageSet:
    return StubImageSet(np.full((638, 1012, 3), 200, np.uint8))
