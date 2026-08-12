"""`probe()` — magic bytes, dimensions, and the limits at the edge (§5.3.2)."""
from __future__ import annotations

import cv2
import numpy as np
import pytest

from cocas.domain.exceptions import ImageDecodeError, ImageTooSmallError
from cocas.infrastructure.images.probe import MAX_UPLOAD_BYTES, probe


def _jpeg(width: int, height: int) -> bytes:
    array = np.full((height, width, 3), 200, dtype=np.uint8)
    ok, buffer = cv2.imencode(".jpg", array)
    assert ok
    return bytes(buffer)


def _png(width: int, height: int) -> bytes:
    array = np.full((height, width, 3), 120, dtype=np.uint8)
    ok, buffer = cv2.imencode(".png", array)
    assert ok
    return bytes(buffer)


class TestAcceptance:
    def test_reads_jpeg_dimensions(self) -> None:
        result = probe(_jpeg(900, 600))
        assert (result.width_px, result.height_px) == (900, 600)
        assert result.mime_type == "image/jpeg"

    def test_reads_png_dimensions(self) -> None:
        result = probe(_png(640, 480))
        assert (result.width_px, result.height_px) == (640, 480)
        assert result.mime_type == "image/png"

    def test_size_bytes_is_the_upload_not_the_decoded_bitmap(self) -> None:
        data = _jpeg(900, 600)
        assert probe(data).size_bytes == len(data)


class TestRejection:
    def test_empty_upload(self) -> None:
        with pytest.raises(ImageDecodeError):
            probe(b"")

    def test_unknown_signature(self) -> None:
        with pytest.raises(ImageDecodeError):
            probe(b"MZ\x90\x00" + b"\x00" * 1024)

    def test_mime_type_comes_from_the_bytes_not_the_extension(self) -> None:
        """⭐ `COCAS-3003`. An executable renamed `front.jpg` still arrives with
        `Content-Type: image/jpeg` — only the first bytes disagree, so only the
        first bytes are consulted."""
        with pytest.raises(ImageDecodeError):
            probe(b"MZ" + _jpeg(900, 600)[2:])

    def test_truncated_jpeg_with_valid_magic(self) -> None:
        """Magic bytes alone prove nothing; the decode is part of validation."""
        with pytest.raises(ImageDecodeError):
            probe(_jpeg(900, 600)[:64])

    def test_oversized_upload(self) -> None:
        with pytest.raises(ImageDecodeError):
            probe(b"\xff\xd8\xff" + b"\x00" * MAX_UPLOAD_BYTES)

    def test_image_below_the_minimum_edge(self) -> None:
        with pytest.raises(ImageTooSmallError):
            probe(_jpeg(200, 200))
