"""`IQrDecoder` (Port 5) production implementation — §7.4.3.

⭐ Three attempts, stopping at the first success. The order was measured on 53
real CCCD photos, not assumed: the native-resolution original wins most often,
the 2x upscale of `v1` recovers cards that shrank below the decoder's module
resolution, and the sharpened top-right crop catches soft-focus shots.

⭐ Never raises. A missing or unreadable QR is a normal outcome (§7.3) — the MRZ
and OCR channels are designed to compensate.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, cast

import cv2
import zxingcpp
from loguru import logger

from cocas.domain.enums.field_key import FieldKey
from cocas.domain.ports.ocr import ImageData, QrExtractionResult

from ..preprocessing.image_data import BgrArray, NumpyImageData

if TYPE_CHECKING:
    from cocas.domain.ports.ocr import PreprocessedImageSet

_READ_OPTIONS = {
    "formats": zxingcpp.BarcodeFormat.QRCode,
    "try_rotate": True,
    "try_downscale": True,
    "try_invert": True,
}

_CORNER_WIDTH = 0.55
_CORNER_HEIGHT = 0.55

ID_NUMBER_LENGTH = 12
DATE_LENGTH = 8
_MIN_PAYLOAD_PARTS = 7

_FIELD_BY_POSITION = {
    0: FieldKey.ID_NUMBER,
    2: FieldKey.FULL_NAME,
    3: FieldKey.DATE_OF_BIRTH,
    6: FieldKey.ISSUE_DATE,
}
_DATE_POSITIONS = (3, 6)


class ZxingQrDecoder:
    """Decode the front-side QR and split its payload into business fields."""

    def decode(self, image_set: PreprocessedImageSet) -> QrExtractionResult:
        """Run the attempt chain and parse whatever payload comes back.

        Returns `available=False` when no attempt produced a payload; the
        `attempts` count reports how many were spent.
        """
        for attempt, build in enumerate(
            (self._native, self._upscaled_v1, self._sharpened_corner), start=1
        ):
            try:
                image = build(image_set)
            except Exception:
                logger.opt(exception=True).debug(
                    "QR attempt {attempt} could not build its image", attempt=attempt
                )
                continue

            payload = _read_barcode(image)
            if payload is not None:
                return _parse_payload(payload, attempt)

        return QrExtractionResult(available=False, attempts=3)

    def _native(self, image_set: PreprocessedImageSet) -> BgrArray:
        return _array_of(image_set.v0)

    def _upscaled_v1(self, image_set: PreprocessedImageSet) -> BgrArray:
        return _upscale(_array_of(image_set.v1), 2)

    def _sharpened_corner(self, image_set: PreprocessedImageSet) -> BgrArray:
        return _upscale(_sharpen(_top_right(_array_of(image_set.v0))), 3)


def _array_of(image: ImageData) -> BgrArray:
    return cast(NumpyImageData, image).array


def _read_barcode(image: BgrArray) -> str | None:
    if image.size == 0:
        return None
    try:
        results = zxingcpp.read_barcodes(image, **_READ_OPTIONS)
    except Exception:
        logger.opt(exception=True).debug("QR decoder raised while reading")
        return None
    for result in results:
        if result.text:
            return str(result.text)
    return None


def _upscale(image: BgrArray, factor: int) -> BgrArray:
    height, width = image.shape[:2]
    resized = cv2.resize(
        image, (width * factor, height * factor), interpolation=cv2.INTER_CUBIC
    )
    return cast(BgrArray, resized)


def _top_right(image: BgrArray) -> BgrArray:
    height, width = image.shape[:2]
    return image[
        0 : int(height * _CORNER_HEIGHT), int(width * (1.0 - _CORNER_WIDTH)) : width
    ]


def _sharpen(image: BgrArray) -> BgrArray:
    blurred = cv2.GaussianBlur(image, (0, 0), 3)
    return cast(BgrArray, cv2.addWeighted(image, 1.6, blurred, -0.6, 0))


def _parse_payload(payload: str, attempts: int) -> QrExtractionResult:
    """Map a decoded payload onto `FieldKey`s, refusing layouts it cannot vouch for.

    ⭐ An unrecognized layout yields `layout_recognized=False` with no fields
    rather than guessed values: when the card format changes, the channel goes
    quiet instead of feeding wrong data into fusion.
    """
    parts = payload.split("|")

    if not _layout_is_plausible(parts):
        logger.warning(
            "QR payload layout not recognized: {count} parts",
            count=len(parts),
            qr_payload=payload,
        )
        return QrExtractionResult(
            available=True,
            raw_payload=payload,
            layout_recognized=False,
            attempts=attempts,
        )

    fields = {
        key: parts[position].strip()
        for position, key in _FIELD_BY_POSITION.items()
        if parts[position].strip()
    }
    return QrExtractionResult(
        available=True,
        raw_payload=payload,
        fields=fields,
        layout_recognized=True,
        attempts=attempts,
    )


def _layout_is_plausible(parts: list[str]) -> bool:
    """⭐ Mandatory sanity check (§7.4.3) before any field is trusted.

    Real payloads carry 7 populated parts; 4 trailing empty parts were observed
    on some cards, so extra blanks are tolerated but extra *content* is not.
    """
    if len(parts) < _MIN_PAYLOAD_PARTS:
        return False
    if any(part.strip() for part in parts[_MIN_PAYLOAD_PARTS:]):
        return False

    identifier = parts[0].strip()
    if len(identifier) != ID_NUMBER_LENGTH or not identifier.isdigit():
        return False

    return all(_is_ddmmyyyy(parts[position].strip()) for position in _DATE_POSITIONS)


def _is_ddmmyyyy(value: str) -> bool:
    if len(value) != DATE_LENGTH or not value.isdigit():
        return False
    day, month = int(value[0:2]), int(value[2:4])
    return 1 <= day <= 31 and 1 <= month <= 12
