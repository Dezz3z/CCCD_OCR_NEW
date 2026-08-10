"""`IOcrEngine` + `IRegionRecognizer` (Ports 1 & 2) on PaddleOCR — §7.4.5.

⭐ **The P-01 seam.** PaddleOCR silently downloads any model it cannot find,
at runtime, from the internet. This adapter makes that impossible: it resolves
`det`/`rec`/`cls` directories itself, verifies they hold real weights, and only
then constructs `PaddleOCR` with all three paths pinned. A missing model is an
`OcrEngineUnavailableError` at `warm_up()` — never a download.

Run `scripts/fetch_ocr_models.py` once to populate `resources/ocr-models/`.

⭐ **What `lang='vi'` actually gets you** (traced in paddleocr 2.9.1, then
confirmed against the CDN):

| Slot | Resolved model | Reality |
|---|---|---|
| `det` | `en_PP-OCRv3_det` | `parse_lang` sends every latin language to `det_lang='en'` |
| `rec` | `latin_PP-OCRv3_rec` | ⭐ **PP-OCRv3**, and its charset is `latin_dict.txt` |
| `cls` | `ch_ppocr_mobile_v2.0_cls` | language-independent |

⚠️ `latin_dict.txt` holds 4 of the 42 accented Vietnamese capitals, so the
recognizer has **no output class** for `Ả Ấ Ầ Ă Ế Ộ Ơ Ư Ỳ …`. `vi_dict.txt`
(42/42) ships in the package but no model matches it — `vi_PP-OCRv3_rec_infer`
returns HTTP 404. Names therefore come back stripped of diacritics rather than
wrong-but-accented, which is the failure mode fusion can actually handle: the
QR channel (source weight 1.00) carries the accented name whenever it decodes.

⭐ Blocking calls stay blocking. Recognition is CPU-bound; wrapping it in a
thread pool is the Application layer's job (ADR-06), so this adapter only
guarantees it is safe to call from one — hence the lock around inference.
"""
from __future__ import annotations

import threading
import time
import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import numpy as np
from loguru import logger

from cocas.domain.exceptions import (
    ImageDecodeError,
    OcrEngineUnavailableError,
    OcrTimeoutError,
)
from cocas.domain.ports.ocr import EngineInfo, ImageData, RelativeBox, TextRegion

from ..preprocessing.image_data import BgrArray, NumpyImageData

if TYPE_CHECKING:
    from cocas.domain.ports.ocr import OcrOptions

ENGINE_NAME = "PaddleOCR"
DEFAULT_LANGUAGE = "vi"
DEFAULT_TIMEOUT_SECONDS = 20.0

# Every inference model directory must contain these two files.
_REQUIRED_MODEL_FILES = ("inference.pdmodel", "inference.pdiparams")
_MODEL_SLOTS = ("det", "rec", "cls")

# ⭐ The dictionary `lang='vi'` really uses. Named explicitly so the packaged app
# never reads it out of site-packages, and so the swap to a Vietnamese-capable
# dictionary is a one-line change the day a matching model exists.
DEFAULT_DICT_NAME = "latin_dict.txt"

# Regions whose vertical centres fall within this fraction of the median region
# height belong to the same line of text.
_LINE_TOLERANCE_RATIO = 0.6

_MIN_USABLE_EDGE = 2


class PaddleOcrAdapter:
    """PP-OCR detection + recognition + angle classification, offline only."""

    def __init__(
        self,
        models_dir: Path | str,
        *,
        cpu_threads: int | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        language: str = DEFAULT_LANGUAGE,
        dict_name: str = DEFAULT_DICT_NAME,
    ) -> None:
        self._models_dir = Path(models_dir)
        self._cpu_threads = cpu_threads if cpu_threads and cpu_threads > 0 else _half_the_cores()
        self._timeout_seconds = timeout_seconds
        self._language = language
        self._dict_name = dict_name
        self._engine: Any | None = None
        self._version = "unknown"
        self._lock = threading.RLock()

    # -- lifecycle ---------------------------------------------------------

    def warm_up(self) -> None:
        """Load the models into memory. Idempotent; safe to call from a thread.

        Raises:
            OcrEngineUnavailableError: a model directory is missing or the
                engine could not be constructed. ⭐ Never falls back to a
                network download (P-01).
        """
        with self._lock:
            if self._engine is not None:
                return

            paths = self._verify_models()
            try:
                import paddleocr
                from paddleocr import PaddleOCR
            except ImportError as error:
                raise OcrEngineUnavailableError(
                    "Không nạp được thư viện PaddleOCR",
                    hint="Cài đặt lại ứng dụng.",
                ) from error

            started = time.monotonic()
            try:
                self._engine = PaddleOCR(
                    lang=self._language,
                    use_angle_cls=True,
                    use_gpu=False,
                    cpu_threads=self._cpu_threads,
                    show_log=False,
                    det_model_dir=str(paths["det"]),
                    rec_model_dir=str(paths["rec"]),
                    cls_model_dir=str(paths["cls"]),
                    rec_char_dict_path=str(paths["dict"]),
                )
            except Exception as error:
                raise OcrEngineUnavailableError(
                    "Không khởi tạo được bộ nhận dạng ký tự",
                    hint="Kiểm tra thư mục model trong phần Chẩn đoán.",
                ) from error

            self._version = str(getattr(paddleocr, "__version__", "unknown"))
            logger.info(
                "OCR engine ready in {elapsed:.1f}s ({threads} threads, models at {path})",
                elapsed=time.monotonic() - started,
                threads=self._cpu_threads,
                path=str(self._models_dir),
            )

    def get_info(self) -> EngineInfo:
        """Report engine identity and whether `warm_up()` has completed."""
        return EngineInfo(
            name=ENGINE_NAME,
            version=self._version,
            languages=[self._language],
            is_ready=self._engine is not None,
            model_path=str(self._models_dir),
        )

    # -- Port 1: IOcrEngine ------------------------------------------------

    def recognize(self, image: ImageData, options: OcrOptions) -> list[TextRegion]:
        """Recognize every text region, in reading order.

        Returns an empty list for an unreadable image — never None (§12.2).
        """
        array = _array_of(image)
        raw = self._run(array, use_angle_cls=options.use_angle_cls)

        regions = [
            region
            for region in _to_regions(raw, array.shape[1], array.shape[0], options.charset_hint)
            if region.confidence >= options.min_confidence
        ]
        return sort_reading_order(regions)

    # -- Port 2: IRegionRecognizer ----------------------------------------

    def recognize_region(
        self, image: ImageData, bbox: RelativeBox, charset_hint: str | None
    ) -> TextRegion | None:
        """Recognize the text inside `bbox`, or None when nothing was read.

        Multiple lines inside the box are joined with newlines in reading
        order — which is exactly the shape `Td1MrzReader` needs for a
        three-line TD1 block.

        ⚠️ `charset_hint` is a post-processing hint, never a decode constraint
        (CLAUDE.md pitfall #3).
        """
        array = _array_of(image)
        crop, origin = _crop(array, bbox)
        if crop is None:
            return None

        # Angle classification is pointless on a crop taken from an image whose
        # orientation the caller already settled, and it costs a model pass.
        raw = self._run(crop, use_angle_cls=False)
        lines = sort_reading_order(
            _to_regions(raw, crop.shape[1], crop.shape[0], charset_hint)
        )
        if not lines:
            return None

        return TextRegion(
            bbox=_union_in_source(lines, crop.shape, origin, array.shape),
            text="\n".join(line.text for line in lines),
            confidence=_weighted_confidence(lines),
        )

    # -- internals ---------------------------------------------------------

    def _verify_models(self) -> dict[str, Path]:
        """⭐ Resolve every model path up front so PaddleOCR never has to guess.

        Leaving any `*_model_dir` unset makes PaddleOCR download it, which is
        exactly the P-01 violation this method exists to prevent.
        """
        resolved: dict[str, Path] = {}
        for slot in _MODEL_SLOTS:
            directory = self._models_dir / slot
            missing = [
                name
                for name in _REQUIRED_MODEL_FILES
                if not (directory / name).is_file()
            ]
            if missing:
                raise OcrEngineUnavailableError(
                    "Thiếu tệp model OCR — không thể nhận dạng tự động",
                    hint="Cài đặt lại ứng dụng để khôi phục thư mục model.",
                    slot=slot,
                    directory=str(directory),
                    missing=missing,
                )
            resolved[slot] = directory

        dictionary = self._models_dir / "dict" / self._dict_name
        if not dictionary.is_file():
            raise OcrEngineUnavailableError(
                "Thiếu bảng ký tự của bộ nhận dạng",
                hint="Cài đặt lại ứng dụng để khôi phục thư mục model.",
                dictionary=str(dictionary),
            )
        resolved["dict"] = dictionary
        return resolved

    def _run(self, array: BgrArray, *, use_angle_cls: bool) -> object:
        """One inference pass, with the engine's readiness and budget enforced."""
        if self._engine is None:
            raise OcrEngineUnavailableError(
                "Bộ nhận dạng chưa sẵn sàng",
                hint="Đợi vài giây rồi thử lại.",
            )
        if array.ndim != 3 or min(array.shape[:2]) < _MIN_USABLE_EDGE:
            raise ImageDecodeError(
                "Ảnh không hợp lệ để nhận dạng", shape=tuple(array.shape)
            )

        started = time.monotonic()
        try:
            with self._lock:
                raw = self._engine.ocr(array, cls=use_angle_cls)
        except Exception as error:
            raise OcrEngineUnavailableError(
                "Bộ nhận dạng gặp lỗi khi xử lý ảnh",
                hint="Thử lại hoặc nhập tay các trường.",
            ) from error

        elapsed = time.monotonic() - started
        if elapsed > self._timeout_seconds:
            # ⭐ A budget check after the fact, not a cancellation: PaddleOCR
            # offers no interrupt hook, and killing the thread mid-inference
            # would corrupt predictor state shared with every later call.
            raise OcrTimeoutError(
                "Nhận dạng ảnh quá lâu",
                hint="Thử ảnh có kích thước nhỏ hơn.",
                elapsed_seconds=round(elapsed, 2),
                budget_seconds=self._timeout_seconds,
            )
        return raw


# ============================================================================
# Pure helpers — no engine required, so they are unit-testable on their own
# ============================================================================


def _half_the_cores() -> int:
    """Default `ocr.cpu_threads`: half the machine, so the UI keeps running."""
    import os

    return max(1, (os.cpu_count() or 2) // 2)


def _array_of(image: ImageData) -> BgrArray:
    if isinstance(image, NumpyImageData):
        return image.array
    array = getattr(image, "array", None)
    if not isinstance(array, np.ndarray):
        raise ImageDecodeError("Ảnh không ở định dạng numpy dùng được")
    return cast(BgrArray, array)


def parse_charset(hint: str) -> frozenset[str]:
    """Expand a charset spec like `A-Z0-9<` into the set of characters it allows."""
    characters: set[str] = set()
    index = 0
    while index < len(hint):
        if index + 2 < len(hint) and hint[index + 1] == "-" and hint[index] <= hint[index + 2]:
            characters.update(
                chr(code) for code in range(ord(hint[index]), ord(hint[index + 2]) + 1)
            )
            index += 3
        else:
            characters.add(hint[index])
            index += 1
    return frozenset(characters)


def apply_charset_hint(text: str, hint: str | None) -> str:
    """Apply a charset hint ⭐ **without deleting anything**.

    Deleting out-of-charset characters is the obvious reading of "post-processing
    filter", and it is the wrong one. Every caller that passes a hint does its
    own *position-based* arithmetic on the result — `Td1MrzReader` reads the
    citizen id from line 1 columns 15–26. Dropping one hallucinated character
    shifts every field after it and yields six confidently-wrong values; mapping
    it to filler, which the channel's own table already does, corrupts only the
    field that contained it. With False Confidence capped at 0.5% that is not a
    close call.

    So the hint does the one thing that is safe at this layer: case folding,
    when the allowed set has no lowercase letters.
    """
    if not hint:
        return text
    allowed = parse_charset(hint)
    if any(character.islower() for character in allowed):
        return text
    return text.upper()


def _to_regions(
    raw: object, width: int, height: int, charset_hint: str | None
) -> list[TextRegion]:
    """Convert PaddleOCR's nested output into `TextRegion`s.

    PaddleOCR returns one entry per input image, each a list of
    `[polygon, (text, score)]` — or None when it found nothing.
    """
    if not isinstance(raw, list) or not raw:
        return []
    page = raw[0]
    if not isinstance(page, list):
        return []

    regions: list[TextRegion] = []
    for item in page:
        parsed = _parse_item(item)
        if parsed is None:
            continue
        polygon, text, score = parsed
        normalized = apply_charset_hint(unicodedata.normalize("NFC", text).strip(), charset_hint)
        if not normalized:
            continue
        regions.append(
            TextRegion(
                bbox=to_relative_box(polygon, width, height),
                text=normalized,
                confidence=score,
            )
        )
    return regions


def _parse_item(item: object) -> tuple[list[tuple[float, float]], str, float] | None:
    if not isinstance(item, list | tuple) or len(item) < 2:
        return None
    polygon_raw, payload = item[0], item[1]
    if not isinstance(payload, list | tuple) or len(payload) < 2:
        return None
    try:
        polygon = [(float(point[0]), float(point[1])) for point in polygon_raw]
        return polygon, str(payload[0]), float(payload[1])
    except (TypeError, ValueError, IndexError):
        logger.debug("Skipping unparsable OCR result item")
        return None


def to_relative_box(
    polygon: list[tuple[float, float]], width: int, height: int
) -> RelativeBox:
    """Axis-aligned bounds of a detection polygon, in relative 0..1 coordinates.

    ⭐ Relative, never pixels: the box has to stay meaningful after the image
    is resized or warped, because the UI draws it on a different rendition
    than the one recognition ran on (§7.3 `RelativeBox`).
    """
    if not polygon or width <= 0 or height <= 0:
        return RelativeBox(x=0.0, y=0.0, w=0.0, h=0.0)

    xs = [point[0] / width for point in polygon]
    ys = [point[1] / height for point in polygon]
    left, right = _clamp(min(xs)), _clamp(max(xs))
    top, bottom = _clamp(min(ys)), _clamp(max(ys))
    return RelativeBox(x=left, y=top, w=right - left, h=bottom - top)


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def sort_reading_order(regions: list[TextRegion]) -> list[TextRegion]:
    """Order regions top-to-bottom, then left-to-right within each line.

    Sorting on `y` alone scrambles any card where two fields sit side by side;
    regions are grouped into lines first, using the median region height as the
    tolerance so the grouping adapts to the image's own text size.
    """
    if len(regions) < 2:
        return list(regions)

    heights = sorted(region.bbox.h for region in regions)
    tolerance = max(heights[len(heights) // 2] * _LINE_TOLERANCE_RATIO, 1e-6)

    by_vertical = sorted(regions, key=_centre_y)
    lines: list[list[TextRegion]] = [[by_vertical[0]]]
    line_centre = _centre_y(by_vertical[0])

    for region in by_vertical[1:]:
        centre = _centre_y(region)
        if centre - line_centre <= tolerance:
            lines[-1].append(region)
        else:
            lines.append([region])
            line_centre = centre

    return [
        region for line in lines for region in sorted(line, key=lambda item: item.bbox.x)
    ]


def _centre_y(region: TextRegion) -> float:
    return region.bbox.y + region.bbox.h / 2


def _weighted_confidence(regions: list[TextRegion]) -> float:
    """Mean confidence weighted by text length — a long line counts for more."""
    total_length = sum(len(region.text) for region in regions)
    if total_length == 0:
        return 0.0
    weighted = sum(region.confidence * len(region.text) for region in regions)
    return round(weighted / total_length, 4)


def _crop(array: BgrArray, bbox: RelativeBox) -> tuple[BgrArray | None, tuple[int, int]]:
    """Cut `bbox` out of the image; returns (crop, top-left pixel origin)."""
    height, width = array.shape[:2]
    left = max(0, min(width - 1, int(round(bbox.x * width))))
    top = max(0, min(height - 1, int(round(bbox.y * height))))
    right = max(left, min(width, int(round((bbox.x + bbox.w) * width))))
    bottom = max(top, min(height, int(round((bbox.y + bbox.h) * height))))

    if right - left < _MIN_USABLE_EDGE or bottom - top < _MIN_USABLE_EDGE:
        return None, (left, top)
    return np.ascontiguousarray(array[top:bottom, left:right]), (left, top)


def _union_in_source(
    regions: list[TextRegion],
    crop_shape: tuple[int, ...],
    origin: tuple[int, int],
    source_shape: tuple[int, ...],
) -> RelativeBox:
    """Tight box around everything found in the crop, in SOURCE image coordinates.

    Reporting the crop's own box back would tell the UI to highlight the whole
    search band; the union of what was actually read is what a user wants to see.
    """
    crop_height, crop_width = crop_shape[0], crop_shape[1]
    source_height, source_width = source_shape[0], source_shape[1]
    left_offset, top_offset = origin

    lefts = [region.bbox.x * crop_width + left_offset for region in regions]
    tops = [region.bbox.y * crop_height + top_offset for region in regions]
    rights = [
        (region.bbox.x + region.bbox.w) * crop_width + left_offset for region in regions
    ]
    bottoms = [
        (region.bbox.y + region.bbox.h) * crop_height + top_offset for region in regions
    ]

    left, right = _clamp(min(lefts) / source_width), _clamp(max(rights) / source_width)
    top, bottom = _clamp(min(tops) / source_height), _clamp(max(bottoms) / source_height)
    return RelativeBox(x=left, y=top, w=right - left, h=bottom - top)
