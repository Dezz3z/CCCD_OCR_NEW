"""`IQrDecoder` (Port 5) production implementation — §7.4.3.

⭐ Five attempts, stopping at the first success. The order was measured on 53
real CCCD photos, not assumed: the native-resolution original wins most often,
the 2x upscale of `v1` recovers cards that shrank below the decoder's module
resolution, and the sharpened top-right crop catches soft-focus shots.

⭐ **Attempts 4 and 5 read the blue channel, and that is the whole point of
them.** A CCCD's background is a fine turquoise guilloche that runs straight
through the QR. Cyan is bright in blue and dark in red, so splitting the channel
off erases the interference while the near-black QR modules stay dark; plain
grayscale mixes it back in at 0.114 weight and the decoder never locks on.
Measured on the 3 cards that all of attempts 1–3 refused: 2 of them decode this
way, taking the sample from 18/21 to **20/21 (95.2%)** of the images that carry
a QR at all, with **no card lost** and +43 ms/image.

⚠️ Attempt 3 keeps `sharpen 1.6 → 3x` even though `2.5 → 4x` reads one more
card: swapping it *loses* a different one that only attempt 3 has ever decoded.
Appending beats tuning here, which is why the chain grew instead of changing.

⭐ Never raises. A missing or unreadable QR is a normal outcome (§7.3) — the MRZ
and OCR channels are designed to compensate.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, cast

import cv2
import zxingcpp
from cv2.typing import MatLike
from loguru import logger

from cocas.domain.enums.field_key import FieldKey
from cocas.domain.ports.ocr import ImageData, QrExtractionResult

from ..preprocessing.cv_types import GrayArray, as_bgr, as_gray
from ..preprocessing.image_data import BgrArray, NumpyImageData

if TYPE_CHECKING:
    from collections.abc import Callable

    from cocas.domain.ports.ocr import PreprocessedImageSet

    # An attempt's image builder. Single- and three-channel renditions are the
    # same type to the checker; the return alias is what tells the reader which
    # one an attempt produces.
    _Builder = Callable[[PreprocessedImageSet], BgrArray | GrayArray]

# ⚠️ Passed as explicit keywords, never unpacked from a dict: a mixed-value
# dict infers as `dict[str, int]` and every one of `read_barcodes`' typed
# parameters then reads as a type error.
#
# `BarcodeFormats`, not `BarcodeFormat` — the singular enum member works at
# runtime but the parameter is the set type, and `|` on the enum is deprecated.
_QR_FORMAT = zxingcpp.BarcodeFormats(zxingcpp.BarcodeFormat.QRCode)

# zxing-cpp's own default. Named here so every attempt states its binarizer
# rather than one attempt looking special for passing the argument.
_LOCAL_AVERAGE = zxingcpp.Binarizer.LocalAverage

# ⭐ Pairs with the blue-channel crop. `LocalAverage` adapts its threshold to a
# small neighbourhood, so a guilloche line crossing the QR drags the local
# threshold with it; a single global threshold over a crop that is *only* card
# and QR does not. Measured: the one card no other combination reads.
_GLOBAL_HISTOGRAM = zxingcpp.Binarizer.GlobalHistogram

_CORNER_WIDTH = 0.55
_CORNER_HEIGHT = 0.55

# Unsharp mask strengths: gentle for the BGR crop, harder for the blue channel
# (splitting a channel costs contrast that sharpening puts back).
_SHARPEN_BGR = 1.6
_SHARPEN_BLUE = 2.5

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
        attempts: tuple[tuple[_Builder, zxingcpp.Binarizer], ...] = (
            (self._native, _LOCAL_AVERAGE),
            (self._upscaled_v1, _LOCAL_AVERAGE),
            (self._sharpened_corner, _LOCAL_AVERAGE),
            (self._sharpened_blue_corner, _LOCAL_AVERAGE),
            (self._blue_corner, _GLOBAL_HISTOGRAM),
        )
        for attempt, (build, binarizer) in enumerate(attempts, start=1):
            try:
                image = build(image_set)
            except Exception:
                logger.opt(exception=True).debug(
                    "QR attempt {attempt} could not build its image", attempt=attempt
                )
                continue

            payload = _read_barcode(image, binarizer)
            if payload is not None:
                return _parse_payload(payload, attempt)

        return QrExtractionResult(available=False, attempts=len(attempts))

    def _native(self, image_set: PreprocessedImageSet) -> BgrArray:
        return _array_of(image_set.v0)

    def _upscaled_v1(self, image_set: PreprocessedImageSet) -> BgrArray:
        return _upscale(_array_of(image_set.v1), 2)

    def _sharpened_corner(self, image_set: PreprocessedImageSet) -> BgrArray:
        return _upscale(_sharpen(_top_right(_array_of(image_set.v0)), _SHARPEN_BGR), 3)

    def _sharpened_blue_corner(self, image_set: PreprocessedImageSet) -> GrayArray:
        corner = _blue_channel(_top_right(_array_of(image_set.v0)))
        return _upscale_gray(_sharpen_gray(corner, _SHARPEN_BLUE), 4)

    def _blue_corner(self, image_set: PreprocessedImageSet) -> GrayArray:
        return _upscale_gray(_blue_channel(_top_right(_array_of(image_set.v0))), 4)


def _array_of(image: ImageData) -> BgrArray:
    return cast(NumpyImageData, image).array


def _read_barcode(
    image: BgrArray | GrayArray, binarizer: zxingcpp.Binarizer
) -> str | None:
    if image.size == 0:
        return None
    try:
        results = zxingcpp.read_barcodes(
            image,
            formats=_QR_FORMAT,
            binarizer=binarizer,
            try_rotate=True,
            try_downscale=True,
            try_invert=True,
        )
    except Exception:
        logger.opt(exception=True).debug("QR decoder raised while reading")
        return None
    for result in results:
        if result.text:
            return str(result.text)
    return None


def _upscale(image: BgrArray, factor: int) -> BgrArray:
    return as_bgr(_resize(image, factor))


def _upscale_gray(image: GrayArray, factor: int) -> GrayArray:
    return as_gray(_resize(image, factor))


def _resize(image: BgrArray | GrayArray, factor: int) -> MatLike:
    height, width = image.shape[:2]
    return cv2.resize(
        image, (width * factor, height * factor), interpolation=cv2.INTER_CUBIC
    )


def _top_right(image: BgrArray) -> BgrArray:
    height, width = image.shape[:2]
    return image[
        0 : int(height * _CORNER_HEIGHT), int(width * (1.0 - _CORNER_WIDTH)) : width
    ]


def _blue_channel(image: BgrArray) -> GrayArray:
    """The B of BGR — where a turquoise guilloche is bright and the QR is not."""
    return as_gray(cv2.split(image)[0])


def _sharpen(image: BgrArray, amount: float) -> BgrArray:
    return as_bgr(_unsharp(image, amount))


def _sharpen_gray(image: GrayArray, amount: float) -> GrayArray:
    return as_gray(_unsharp(image, amount))


def _unsharp(image: BgrArray | GrayArray, amount: float) -> MatLike:
    blurred = cv2.GaussianBlur(image, (0, 0), 3)
    return cv2.addWeighted(image, amount, blurred, -(amount - 1.0), 0)


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
