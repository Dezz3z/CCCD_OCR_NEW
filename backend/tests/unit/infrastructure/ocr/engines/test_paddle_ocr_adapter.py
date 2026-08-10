"""`PaddleOcrAdapter` — the P-01 guard, output normalization, reading order.

⭐ No models and no `paddleocr` import needed: the adapter defers that import to
`warm_up()`, and everything below either exercises the refusal path or the pure
helpers. That is deliberate — CI must be able to check this adapter on a runner
with no 16 MB model directory.
"""
from __future__ import annotations

import numpy as np
import pytest

from cocas.domain.exceptions import ImageDecodeError, OcrEngineUnavailableError
from cocas.domain.ports.ocr import OcrOptions, RelativeBox, TextRegion
from cocas.infrastructure.ocr.engines import PaddleOcrAdapter
from cocas.infrastructure.ocr.engines import paddle_ocr_adapter as adapter_module
from cocas.infrastructure.ocr.preprocessing.image_data import NumpyImageData


def region(x: float, y: float, w: float = 0.1, h: float = 0.05, text: str = "x") -> TextRegion:
    return TextRegion(bbox=RelativeBox(x, y, w, h), text=text, confidence=0.9)


@pytest.fixture
def models_dir(tmp_path):
    """A directory laid out like `resources/ocr-models`, with dummy weights."""
    for slot in ("det", "rec", "cls"):
        directory = tmp_path / slot
        directory.mkdir()
        for name in ("inference.pdmodel", "inference.pdiparams"):
            (directory / name).write_bytes(b"not a real model")
    dictionary = tmp_path / "dict"
    dictionary.mkdir()
    (dictionary / "latin_dict.txt").write_text("a\nb\n", encoding="utf-8")
    return tmp_path


class TestOfflineGuarantee:
    """⭐ P-01: PaddleOCR downloads any model it cannot find. It must never
    get the chance, so a missing directory is an error, not a fetch."""

    def test_refuses_to_start_without_models(self, tmp_path):
        with pytest.raises(OcrEngineUnavailableError):
            PaddleOcrAdapter(tmp_path).warm_up()

    def test_refuses_when_one_slot_is_incomplete(self, models_dir):
        (models_dir / "rec" / "inference.pdiparams").unlink()
        with pytest.raises(OcrEngineUnavailableError) as caught:
            PaddleOcrAdapter(models_dir).warm_up()
        assert caught.value.context["slot"] == "rec"

    def test_refuses_without_the_character_dictionary(self, models_dir):
        (models_dir / "dict" / "latin_dict.txt").unlink()
        with pytest.raises(OcrEngineUnavailableError):
            PaddleOcrAdapter(models_dir).warm_up()

    def test_reports_itself_as_not_ready_before_warm_up(self, models_dir):
        assert PaddleOcrAdapter(models_dir).get_info().is_ready is False

    def test_recognizing_before_warm_up_fails_loudly(self, models_dir):
        image = NumpyImageData(np.zeros((10, 10, 3), np.uint8))
        with pytest.raises(OcrEngineUnavailableError):
            PaddleOcrAdapter(models_dir).recognize(image, OcrOptions())


class TestRelativeBoxes:
    """⭐ Relative, never pixels: the UI draws these on a different rendition
    than recognition ran on."""

    def test_converts_a_detection_polygon(self):
        box = adapter_module.to_relative_box(
            [(100, 50), (300, 50), (300, 100), (100, 100)], width=1000, height=500
        )
        assert (box.x, box.y, box.w, box.h) == pytest.approx((0.1, 0.1, 0.2, 0.1))

    def test_clamps_a_polygon_that_spills_off_the_image(self):
        box = adapter_module.to_relative_box(
            [(-20, -20), (1200, -20), (1200, 600), (-20, 600)], width=1000, height=500
        )
        assert (box.x, box.y) == (0.0, 0.0)
        assert box.x + box.w <= 1.0
        assert box.y + box.h <= 1.0

    def test_an_empty_polygon_yields_an_empty_box(self):
        assert adapter_module.to_relative_box([], 100, 100).w == 0.0


class TestReadingOrder:
    def test_orders_top_to_bottom(self):
        ordered = adapter_module.sort_reading_order([region(0.1, 0.8), region(0.1, 0.1)])
        assert [r.bbox.y for r in ordered] == [0.1, 0.8]

    def test_orders_left_to_right_within_a_line(self):
        """⭐ Sorting on y alone scrambles any card with two fields side by side
        — `Giới tính` and `Quốc tịch` share a line on every CCCD front."""
        ordered = adapter_module.sort_reading_order(
            [region(0.6, 0.30, text="right"), region(0.1, 0.31, text="left")]
        )
        assert [r.text for r in ordered] == ["left", "right"]

    def test_a_taller_gap_starts_a_new_line(self):
        ordered = adapter_module.sort_reading_order(
            [region(0.6, 0.10, text="a"), region(0.1, 0.50, text="b")]
        )
        assert [r.text for r in ordered] == ["a", "b"]

    def test_a_single_region_is_returned_unchanged(self):
        only = [region(0.5, 0.5)]
        assert adapter_module.sort_reading_order(only) == only


class TestCharsetHint:
    """⭐ The hint never deletes characters. Callers do position arithmetic on
    the result — `Td1MrzReader` reads the citizen id from columns 15–26 — so
    dropping one hallucinated glyph shifts every field after it and produces
    six confidently wrong values instead of one."""

    def test_expands_a_range_specification(self):
        assert adapter_module.parse_charset("A-C0-2<") == frozenset("ABC012<")

    def test_uppercases_when_the_hint_has_no_lowercase(self):
        assert adapter_module.apply_charset_hint("idvnm", "A-Z0-9<") == "IDVNM"

    def test_keeps_characters_outside_the_hint(self):
        assert adapter_module.apply_charset_hint("IDVNMỘ42", "A-Z0-9<") == "IDVNMỘ42"

    def test_preserves_length(self):
        text = "ID VNM Ộ 42"
        assert len(adapter_module.apply_charset_hint(text, "A-Z0-9<")) == len(text)

    def test_no_hint_leaves_text_alone(self):
        assert adapter_module.apply_charset_hint("Mixed Case", None) == "Mixed Case"


class TestResultParsing:
    def test_converts_paddles_nested_output(self):
        raw = [[[[[10, 10], [90, 10], [90, 30], [10, 30]], ("Xin chào", 0.87)]]]
        regions = adapter_module._to_regions(raw, 100, 100, None)
        assert [(r.text, r.confidence) for r in regions] == [("Xin chào", 0.87)]

    def test_normalizes_text_to_nfc(self):
        decomposed = "Hà"  # `Hà` as base letter plus combining grave
        raw = [[[[[0, 0], [10, 0], [10, 5], [0, 5]], (decomposed, 0.9)]]]
        assert adapter_module._to_regions(raw, 100, 100, None)[0].text == "Hà"

    def test_an_empty_page_yields_no_regions(self):
        assert adapter_module._to_regions([None], 100, 100, None) == []

    def test_unparsable_items_are_skipped_not_raised(self):
        raw = [[["not a polygon"], [[[0, 0], [9, 0], [9, 4], [0, 4]], ("ok", 0.9)]]]
        assert [r.text for r in adapter_module._to_regions(raw, 100, 100, None)] == ["ok"]

    def test_blank_text_is_dropped(self):
        raw = [[[[[0, 0], [9, 0], [9, 4], [0, 4]], ("   ", 0.9)]]]
        assert adapter_module._to_regions(raw, 100, 100, None) == []


class TestCropping:
    def test_returns_the_requested_window(self):
        array = np.arange(100 * 200 * 3, dtype=np.uint8).reshape(100, 200, 3)
        crop, origin = adapter_module._crop(array, RelativeBox(0.5, 0.5, 0.5, 0.5))
        assert crop is not None
        assert crop.shape[:2] == (50, 100)
        assert origin == (100, 50)

    def test_a_degenerate_box_yields_nothing(self):
        array = np.zeros((100, 200, 3), np.uint8)
        crop, _ = adapter_module._crop(array, RelativeBox(0.5, 0.5, 0.0, 0.0))
        assert crop is None

    def test_a_box_reaching_past_the_edge_is_clamped(self):
        array = np.zeros((100, 200, 3), np.uint8)
        crop, _ = adapter_module._crop(array, RelativeBox(0.9, 0.9, 0.5, 0.5))
        assert crop is not None
        assert crop.shape[0] <= 100 and crop.shape[1] <= 200


class TestImageValidation:
    def test_a_non_numpy_image_is_a_decode_error(self):
        class NotAnImage:
            width = 10
            height = 10

        with pytest.raises(ImageDecodeError):
            adapter_module._array_of(NotAnImage())
