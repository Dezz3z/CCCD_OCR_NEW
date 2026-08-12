"""Validate and measure an uploaded image before it is stored (§5.3.2).

⭐ **Magic bytes, not the filename and not the `Content-Type`.** §5.1.5 gives
`COCAS-3003` its own code precisely because a browser-supplied MIME type is
attacker-controlled: `evil.exe` renamed to `front.jpg` arrives with
`image/jpeg` and nothing in the HTTP layer disagrees. The first bytes of the
file are the only claim the uploader does not get to make.

⚠️ Decoding is also part of validation. A file can start with `\\xff\\xd8\\xff`
and still be truncated garbage; `cv2.imdecode` returning `None` is the check
that the bytes are an image, and it is also where the dimensions come from —
so there is exactly one pass and one source for both answers.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from cocas.domain.exceptions import ImageDecodeError, ImageTooSmallError
from cocas.infrastructure.ocr.preprocessing.cv_types import as_optional_bgr

#: `(magic prefix, mime type)`, longest-first so JPEG's 3-byte prefix cannot
#: shadow a longer signature that happens to start the same way.
_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)

#: §5.5 #6 — 10 MB, matching `CardImage.MAX_SIZE_BYTES`.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

#: `CardImage.__post_init__` rejects outside 320–12000 px; refuse here too so
#: the caller gets `COCAS-3005` instead of a generic business-rule violation.
MIN_EDGE_PX = 320
MAX_EDGE_PX = 12000

#: A 200-megapixel image decodes to ~600 MB of BGR. §5.1.5 `COCAS-3006`.
MAX_PIXELS = 60_000_000


@dataclass(frozen=True, slots=True)
class ProbedImage:
    """What the uploader is actually holding."""

    mime_type: str
    width_px: int
    height_px: int
    size_bytes: int


def probe(data: bytes) -> ProbedImage:
    """Validate `data` as an image and measure it, or raise.

    Raises:
        ImageDecodeError: empty, oversized, unknown signature, or undecodable.
        ImageTooSmallError: decoded but outside the accepted edge range.
    """
    if not data:
        raise ImageDecodeError("Không đọc được ảnh: tệp rỗng.", hint="Hãy chọn lại ảnh.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImageDecodeError(
            f"Ảnh vượt quá {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
            hint="Chụp lại ở độ phân giải thấp hơn, hoặc nén ảnh trước khi tải lên.",
        )

    mime_type = next(
        (mime for prefix, mime in _SIGNATURES if data.startswith(prefix)), None
    )
    if mime_type is None:
        raise ImageDecodeError(
            "Tệp không phải ảnh JPG hoặc PNG.",
            hint="Chỉ hỗ trợ ảnh .jpg và .png — hãy chọn lại tệp.",
        )

    decoded = as_optional_bgr(
        cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    )
    if decoded is None:
        raise ImageDecodeError(
            "Ảnh bị hỏng hoặc không giải mã được.",
            hint="Mở thử ảnh bằng trình xem ảnh; nếu không mở được, hãy chụp lại.",
        )

    height_px, width_px = int(decoded.shape[0]), int(decoded.shape[1])
    if width_px * height_px > MAX_PIXELS:
        raise ImageDecodeError(
            "Ảnh có số điểm ảnh vượt mức cho phép.",
            hint="Chụp lại ở độ phân giải thấp hơn.",
        )
    if not (MIN_EDGE_PX <= width_px <= MAX_EDGE_PX) or not (
        MIN_EDGE_PX <= height_px <= MAX_EDGE_PX
    ):
        raise ImageTooSmallError(
            f"Kích thước ảnh {width_px}x{height_px} px nằm ngoài phạm vi "
            f"{MIN_EDGE_PX}-{MAX_EDGE_PX} px.",
            hint="Chụp lại sao cho thẻ chiếm phần lớn khung hình.",
        )

    return ProbedImage(
        mime_type=mime_type,
        width_px=width_px,
        height_px=height_px,
        size_bytes=len(data),
    )
