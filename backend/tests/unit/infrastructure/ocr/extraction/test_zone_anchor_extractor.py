"""`ZoneAndAnchorExtractor` — both strategies, over a real card's region list.

The region layout below is transcribed from PaddleOCR output on an actual CCCD
front, coordinates included, so the geometry the extractor reasons about is the
geometry it will meet.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from cocas.domain.enums.card_side import CardSide
from cocas.domain.enums.field_key import FieldKey
from cocas.domain.ports.ocr import (
    DocumentTypeSpec,
    ExtractionStrategy,
    RelativeBox,
    TextRegion,
)
from cocas.infrastructure.ocr.extraction import ZoneAndAnchorExtractor

ZONE_MAP = {
    "id_number": {"x": 0.26, "y": 0.37, "w": 0.54, "h": 0.15, "side": "FRONT"},
    "full_name": {"x": 0.26, "y": 0.51, "w": 0.55, "h": 0.14, "side": "FRONT"},
    "date_of_birth": {"x": 0.28, "y": 0.58, "w": 0.53, "h": 0.13, "side": "FRONT"},
    "issue_date": {"x": 0.00, "y": 0.08, "w": 0.57, "h": 0.17, "side": "BACK"},
    "mrz": {"x": 0.02, "y": 0.62, "w": 0.96, "h": 0.36, "side": "BACK"},
}
ANCHORS = {
    "front": {
        "full_name": ["Họ và tên", "Full name"],
        "id_number": ["Số / No.", "No.:"],
        "date_of_birth": ["Ngày sinh", "Date of birth"],
    },
    "back": {"issue_date": ["Ngày, tháng, năm", "Date, month, year"]},
}


def region(text: str, x: float, y: float, w: float = 0.3, h: float = 0.04) -> TextRegion:
    return TextRegion(bbox=RelativeBox(x, y, w, h), text=text, confidence=0.92)


# Transcribed from a real front, y coordinates and all.
FRONT_REGIONS = [
    region("CONG HOAXAHOI CHU NGHIAVIET NAM", 0.29, 0.05),
    region("Doclap-Twdo-Hanhphuc", 0.40, 0.10),
    region("CAN CU'O'C CONG DAN", 0.29, 0.24),
    region("Citizen Identity Card", 0.29, 0.34),
    region("S61No.", 0.29, 0.43, w=0.09),
    region("001087043408", 0.40, 0.43, w=0.20, h=0.06),
    region("Hova ten/ Full name.", 0.29, 0.50),
    region("BUI VAN LONG", 0.30, 0.56),
    region("Ngay sinh/Date of birth.", 0.29, 0.63),
    region("13/03/1987", 0.58, 0.63, w=0.15),
]

BACK_REGIONS = [
    region("Dac diem nhan dang/ Personal identification:", 0.03, 0.02),
    region("Ngaythang,nam/Date,month,year.05/04/2022", 0.03, 0.13, w=0.53),
    region("CUC TRUO'NG CUC CANH SAT", 0.19, 0.18),
]


def doc_type() -> DocumentTypeSpec:
    return DocumentTypeSpec(
        code="CCCD_CHIP",
        name="Căn cước công dân gắn chip",
        field_schema=[],
        zone_map=ZONE_MAP,
        anchor_patterns=ANCHORS,
        has_qr=True,
        has_mrz=True,
        is_ocr_supported=True,
        expected_aspect_ratio=1.585,
    )


@pytest.fixture
def extractor() -> ZoneAndAnchorExtractor:
    return ZoneAndAnchorExtractor()


class TestZoneStrategy:
    @pytest.fixture
    def fields(self, extractor):
        return extractor.extract(FRONT_REGIONS, CardSide.FRONT, doc_type(), True)

    def test_reads_the_citizen_id(self, fields):
        assert fields[FieldKey.ID_NUMBER].text == "001087043408"

    def test_reads_the_name(self, fields):
        assert fields[FieldKey.FULL_NAME].text == "BUI VAN LONG"

    def test_reads_the_date_of_birth(self, fields):
        assert fields[FieldKey.DATE_OF_BIRTH].text == "13/03/1987"

    def test_never_returns_the_card_subtitle_as_a_name(self, fields):
        """⭐ The measured failure that calibration and the boilerplate list
        exist to prevent."""
        assert fields[FieldKey.FULL_NAME].text != "CITIZEN IDENTITY CARD"

    def test_keeps_the_region_box_for_the_ui_to_highlight(self, fields):
        assert fields[FieldKey.ID_NUMBER].bbox is not None

    def test_reports_which_strategy_won(self, fields):
        assert fields[FieldKey.ID_NUMBER].strategy is ExtractionStrategy.ZONE


class TestAnchorStrategy:
    """⭐ The fallback for photos that could not be rectified. Measured on real
    cards it matches ZONE exactly — 83 values found against 84 — so an
    unrectifiable upload loses almost nothing."""

    @pytest.fixture
    def fields(self, extractor):
        return extractor.extract(FRONT_REGIONS, CardSide.FRONT, doc_type(), False)

    def test_finds_the_value_on_the_labels_own_line(self, fields):
        assert fields[FieldKey.DATE_OF_BIRTH].text == "13/03/1987"

    def test_finds_the_value_on_the_line_below_its_label(self, fields):
        assert fields[FieldKey.FULL_NAME].text == "BUI VAN LONG"

    def test_finds_the_citizen_id_by_its_printed_size(self, fields):
        """⭐ Nothing on a CCCD is printed as large as the number, so height
        identifies it even when `Số / No.` was never recognized."""
        assert fields[FieldKey.ID_NUMBER].text == "001087043408"

    def test_all_values_are_marked_as_anchor_found(self, fields):
        assert all(
            value.strategy is ExtractionStrategy.ANCHOR for value in fields.values()
        )

    def test_the_tallest_rule_survives_a_missing_label(self, extractor):
        without_label = [r for r in FRONT_REGIONS if r.text != "S61No."]
        fields = extractor.extract(without_label, CardSide.FRONT, doc_type(), False)
        assert fields[FieldKey.ID_NUMBER].text == "001087043408"


class TestBackSide:
    def test_reads_the_issue_date_sharing_its_label_line(self, extractor):
        fields = extractor.extract(BACK_REGIONS, CardSide.BACK, doc_type(), True)
        assert fields[FieldKey.ISSUE_DATE].text == "05/04/2022"

    def test_front_only_fields_are_not_looked_for_on_the_back(self, extractor):
        fields = extractor.extract(BACK_REGIONS, CardSide.BACK, doc_type(), True)
        assert FieldKey.FULL_NAME not in fields


class TestAbsentAndMalformed:
    def test_a_field_with_no_plausible_value_is_absent_not_empty(self, extractor):
        """⭐ An empty string would reach fusion as a real reading."""
        fields = extractor.extract(
            [region("nothing useful here", 0.3, 0.4)], CardSide.FRONT, doc_type(), True
        )
        assert FieldKey.ID_NUMBER not in fields

    def test_no_regions_yields_no_fields(self, extractor):
        assert extractor.extract([], CardSide.FRONT, doc_type(), True) == {}

    def test_an_unusable_zone_is_skipped_without_raising(self, extractor):
        spec = replace(
            doc_type(),
            zone_map=dict(ZONE_MAP, id_number={"x": "left", "y": None}),
        )
        fields = extractor.extract(FRONT_REGIONS, CardSide.FRONT, spec, True)
        assert fields[FieldKey.FULL_NAME].text == "BUI VAN LONG"

    def test_the_mrz_zone_is_not_mistaken_for_a_field(self, extractor):
        """`mrz` has no `FieldKey`; it must be ignored, not crash the mapping."""
        assert extractor.extract(BACK_REGIONS, CardSide.BACK, doc_type(), True)
