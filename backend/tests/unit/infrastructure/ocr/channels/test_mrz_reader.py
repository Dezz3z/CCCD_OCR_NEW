"""`Td1MrzReader` — band selection, scoring, and the never-raise contract (§7.4.4).

⭐ Driven by a stub `IRegionRecognizer`, which is the whole point of splitting
that narrow port out of `IOcrEngine`: the MRZ channel is fully testable in week
2, before any real engine exists.
"""
from __future__ import annotations

import numpy as np
import pytest

from cocas.domain.enums.field_key import FieldKey
from cocas.domain.ports.ocr import DocumentTypeSpec, RelativeBox, TextRegion
from cocas.infrastructure.ocr.channels.mrz_reader import (
    CONFIDENCE_CLEAN,
    CONFIDENCE_FAILED,
    CONFIDENCE_REPAIRED,
    Td1MrzReader,
)

from .conftest import REAL_MRZ_LINES, StubImageSet


class StubRecognizer:
    """Returns canned text and remembers the box and hint it was asked for.

    Accepts a list to answer differently per call, which is how the v3-then-v4
    fallback is exercised without a real engine.
    """

    def __init__(self, text: str | list[str | None] | None, *, explode: bool = False) -> None:
        self._texts = list(text) if isinstance(text, list) else [text]
        self._explode = explode
        self.boxes: list[RelativeBox] = []
        self.hints: list[str | None] = []

    def recognize_region(self, image, bbox, charset_hint):
        if self._explode:
            raise RuntimeError("engine died mid-read")
        self.boxes.append(bbox)
        self.hints.append(charset_hint)
        index = min(len(self.boxes) - 1, len(self._texts) - 1)
        answer = self._texts[index]
        return None if answer is None else TextRegion(bbox, answer, 0.9)


def doc_type(*, has_mrz: bool = True, zone_map: dict | None = None) -> DocumentTypeSpec:
    return DocumentTypeSpec(
        code="CCCD_CHIP",
        name="Căn cước công dân gắn chip",
        field_schema=[],
        zone_map=zone_map if zone_map is not None else {},
        anchor_patterns={},
        has_qr=True,
        has_mrz=has_mrz,
        is_ocr_supported=True,
        expected_aspect_ratio=1.585,
    )


@pytest.fixture
def image_set() -> StubImageSet:
    return StubImageSet(np.full((638, 1012, 3), 200, np.uint8))


def read_with(text: str | None, *, warp: bool = True, zone_map=None, explode=False):
    recognizer = StubRecognizer(text, explode=explode)
    image_set = StubImageSet(np.full((638, 1012, 3), 200, np.uint8), warp_succeeded=warp)
    result = Td1MrzReader(recognizer).read(image_set, doc_type(zone_map=zone_map))
    return result, recognizer, image_set


class TestCleanRead:
    @pytest.fixture
    def result(self):
        return read_with("\n".join(REAL_MRZ_LINES))[0]

    def test_reports_the_channel_as_available(self, result):
        assert result.available is True

    def test_validates_every_checksum(self, result):
        assert result.checksum_valid is True

    def test_scores_a_clean_read_highest(self, result):
        assert result.confidence == CONFIDENCE_CLEAN
        assert result.corrections_applied == 0

    def test_supplies_the_expiry_date_no_other_channel_has(self, result):
        assert result.fields[FieldKey.EXPIRY_DATE] == "27022039"

    def test_emits_dates_in_the_same_shape_as_the_qr_channel(self, result):
        """⭐ Otherwise fusion scores two correct readings as a conflict."""
        assert result.fields[FieldKey.DATE_OF_BIRTH] == "27021979"

    def test_reports_the_citizen_id_not_the_old_cmnd(self, result):
        assert result.fields[FieldKey.ID_NUMBER] == "048179002546"

    def test_keeps_the_normalized_lines(self, result):
        assert result.raw_lines == REAL_MRZ_LINES


class TestDegradedRead:
    def test_a_repaired_block_scores_lower_than_a_clean_one(self):
        """A misread `1` as `7`: the check digit still pins the original value."""
        damaged = list(REAL_MRZ_LINES)
        damaged[0] = damaged[0].replace("IDVNM179002546", "IDVNM779002546", 1)
        result = read_with("\n".join(damaged))[0]
        assert result.checksum_valid is True
        assert result.corrections_applied >= 1
        assert result.confidence == CONFIDENCE_REPAIRED

    def test_an_unfixable_block_still_returns_its_values(self):
        """⭐ P-08: the values reach fusion, flagged, rather than vanishing."""
        damaged = list(REAL_MRZ_LINES)
        damaged[0] = "IDVNM1790025462111111111111<<2"
        result = read_with("\n".join(damaged))[0]
        assert result.available is True
        assert result.checksum_valid is False
        assert result.confidence == CONFIDENCE_FAILED
        assert result.fields[FieldKey.DATE_OF_BIRTH] == "27021979"

    def test_a_repair_the_composite_cannot_witness_is_not_trusted(self):
        """⭐ Three edits will satisfy almost any single check digit, so a
        repaired block is only trusted when the whole-block digit agrees."""
        damaged = list(REAL_MRZ_LINES)
        damaged[1] = "7902273F3911111VNM<<<<<<<<<<<2"
        result = read_with("\n".join(damaged))[0]
        assert result.checksum_valid is False

    def test_noise_is_not_reported_as_a_block_at_all(self):
        """⭐ Three lines of nothing must not classify as a TD1 block."""
        result = read_with("\n".join(["9" * 30, "9" * 30, "V" * 30]))[0]
        assert result.available is False

    def test_drops_a_citizen_id_that_is_not_twelve_digits(self):
        """⭐ A failed block still reaches fusion at 0.50 — malformed values
        must never get that far (False Confidence budget)."""
        damaged = list(REAL_MRZ_LINES)
        damaged[0] = "IDVNM1790025462048<<<<<<<<<<<<"
        result = read_with("\n".join(damaged))[0]
        assert FieldKey.ID_NUMBER not in result.fields


class TestAbsentOrUnreadable:
    def test_document_without_an_mrz_is_skipped_entirely(self):
        recognizer = StubRecognizer("\n".join(REAL_MRZ_LINES))
        image_set = StubImageSet(np.full((638, 1012, 3), 200, np.uint8))
        result = Td1MrzReader(recognizer).read(image_set, doc_type(has_mrz=False))
        assert result.available is False
        assert recognizer.boxes == []

    def test_recognizer_finding_nothing_is_not_an_error(self):
        assert read_with(None)[0].available is False

    def test_blank_text_is_not_an_error(self):
        assert read_with("   \n  \n ")[0].available is False

    def test_a_dying_engine_is_reported_not_raised(self):
        assert read_with("x", explode=True)[0].available is False


class TestVariantOrder:
    def test_reads_the_text_variant_first(self):
        """⭐ Measured on 20 real backs: binarizing costs 8 of them outright."""
        _, _, image_set = read_with("\n".join(REAL_MRZ_LINES))
        assert image_set.accessed[0] == "v3"

    def test_never_builds_the_fallback_variant_after_a_clean_read(self):
        _, _, image_set = read_with("\n".join(REAL_MRZ_LINES))
        assert "v4" not in image_set.accessed

    def test_falls_back_to_the_binarized_variant(self):
        result, _, image_set = read_with([None, "\n".join(REAL_MRZ_LINES)])
        assert image_set.accessed == ["v3", "v4"]
        assert result.checksum_valid is True

    def test_prefers_the_variant_whose_checksums_pass(self):
        damaged = list(REAL_MRZ_LINES)
        damaged[0] = "IDVNM1790025462111111111111<<2"
        result, _, _ = read_with(["\n".join(damaged), "\n".join(REAL_MRZ_LINES)])
        assert result.checksum_valid is True
        assert result.raw_lines == REAL_MRZ_LINES


class TestBandSelection:

    def test_passes_the_mrz_charset_hint(self):
        _, recognizer, _ = read_with("\n".join(REAL_MRZ_LINES))
        assert recognizer.hints == ["A-Z0-9<"]

    def test_uses_the_calibrated_zone_when_the_card_was_rectified(self):
        zone = {"mrz": {"x": 0.05, "y": 0.80, "w": 0.90, "h": 0.18}}
        _, recognizer, _ = read_with("\n".join(REAL_MRZ_LINES), zone_map=zone)
        assert recognizer.boxes[0] == RelativeBox(0.05, 0.80, 0.90, 0.18)

    def test_ignores_the_zone_when_the_warp_was_refused(self):
        """⭐ Zone coordinates are meaningless on an image that was never rectified."""
        zone = {"mrz": {"x": 0.05, "y": 0.80, "w": 0.90, "h": 0.18}}
        _, recognizer, _ = read_with(
            "\n".join(REAL_MRZ_LINES), warp=False, zone_map=zone
        )
        assert recognizer.boxes[0] != RelativeBox(0.05, 0.80, 0.90, 0.18)

    def test_falls_back_when_the_zone_map_is_malformed(self):
        zone = {"mrz": {"x": "left", "y": None}}
        result, recognizer, _ = read_with("\n".join(REAL_MRZ_LINES), zone_map=zone)
        assert result.available is True
        assert recognizer.boxes[0].h > 0
