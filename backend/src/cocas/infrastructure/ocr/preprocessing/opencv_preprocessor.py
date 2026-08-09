"""`IImagePreprocessor` (Port 3) production implementation — §7.4.1, §12.4."""
from __future__ import annotations

import cv2
import numpy as np

from cocas.domain.exceptions import ImageDecodeError, ImageTooSmallError
from cocas.domain.ports.ocr import PreprocessProfile

from .image_data import BgrArray
from .variant_set import LazyPreprocessedImageSet

MIN_SHORT_EDGE = 320


class OpenCvPreprocessor:
    """Decodes the upload and hands back its (lazy) variant set.

    Decoding is the only eager work: everything else happens when a channel
    first reaches for the variant it needs.
    """

    def prepare(
        self,
        image_bytes: bytes,
        exif_orientation: int | None,
        profile: PreprocessProfile,
    ) -> LazyPreprocessedImageSet:
        if not image_bytes:
            raise ImageDecodeError(
                "Không đọc được ảnh: tệp rỗng.",
                hint="Hãy tải lại ảnh CCCD.",
            )

        buffer = np.frombuffer(image_bytes, dtype=np.uint8)
        decoded: BgrArray | None = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
        if decoded is None:
            raise ImageDecodeError(
                "Không đọc được ảnh: tệp không phải định dạng ảnh hợp lệ.",
                hint="Hãy dùng ảnh JPG hoặc PNG.",
            )

        short_edge = min(decoded.shape[:2])
        if short_edge < MIN_SHORT_EDGE:
            raise ImageTooSmallError(
                f"Ảnh quá nhỏ: cạnh ngắn chỉ {short_edge} px, "
                f"tối thiểu {MIN_SHORT_EDGE} px.",
                hint="Hãy chụp lại ảnh CCCD ở độ phân giải cao hơn.",
            )

        return LazyPreprocessedImageSet(decoded, exif_orientation, profile)
