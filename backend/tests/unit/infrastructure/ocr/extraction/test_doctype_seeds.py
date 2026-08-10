"""The seeded `zone_map` / `anchor_patterns` for both card generations.

⭐ These are data, not code, and they are the part of the OCR pipeline that has
been wrong most often (§7.4.6, §7.4.7). The checks below are the ones that would
have caught the mistakes actually made: a zone on the wrong side, two anchors
that match each other's line, and an authority listed as boilerplate.

Loaded straight from the migration modules so there is no second copy to drift.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import ClassVar

import pytest

from cocas.domain.enums.field_key import FieldKey
from cocas.infrastructure.ocr.extraction.zone_anchor_extractor import ANCHOR_THRESHOLD
from cocas.infrastructure.ocr.text_matching import is_printed_boilerplate, similarity

_VERSIONS = Path(__file__).resolve().parents[5] / "migrations" / "versions"


def _load(filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(filename, _VERSIONS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cccd_2021() -> ModuleType:
    return _load("20260811_003_seed_doctype.py")


@pytest.fixture(scope="module")
def can_cuoc_2024() -> ModuleType:
    return _load("20260811_009_seed_doctype_2024.py")


@pytest.fixture(params=["2021", "2024"])
def seed(request, cccd_2021, can_cuoc_2024) -> ModuleType:
    return cccd_2021 if request.param == "2021" else can_cuoc_2024


class TestBothGenerations:
    def test_every_zone_names_a_real_field(self, seed):
        keys = {key for key in seed._ZONE_MAP if key != "mrz"}
        assert keys <= {key.value for key in FieldKey}

    def test_every_zone_is_inside_the_frame(self, seed):
        for name, zone in seed._ZONE_MAP.items():
            assert 0.0 <= zone["x"] < zone["x"] + zone["w"] <= 1.0, name
            assert 0.0 <= zone["y"] < zone["y"] + zone["h"] <= 1.0, name

    def test_every_anchored_field_also_has_a_zone(self, seed):
        anchored = {
            key for side in seed._ANCHOR_PATTERNS.values() for key in side
        }
        assert anchored <= set(seed._ZONE_MAP)

    def test_an_anchor_and_its_zone_agree_about_the_side(self, seed):
        for side_key, fields in seed._ANCHOR_PATTERNS.items():
            for field in fields:
                assert seed._ZONE_MAP[field]["side"] == side_key.upper(), field

    def test_the_issuing_authority_is_an_anchor_but_never_boilerplate(self, seed):
        """⭐ It is the `issue_place` VALUE. Listing it as printed text would
        make `find_place` throw the field away."""
        for anchor in seed._ANCHOR_PATTERNS["back"]["issue_place"]:
            assert is_printed_boilerplate(anchor) is False, anchor

    # The two lines every card prints in its largest type — and the ones a short
    # anchor collides with. ⭐ `Số` alone scored 100 against the second.
    HEADER_LINES: ClassVar[list[str]] = [
        "CONG HOA XA HOI CHU NGHIA VIET NAM",
        "SOCIALIST REPUBLIC OF VIET NAM",
    ]

    def test_no_anchor_matches_the_republic_header(self, seed):
        """⭐ The measured hazard, not a proxy for it.

        A short anchor is only a problem when it collides with something, and
        this is what it collides with: `partial_ratio` scores the best-matching
        substring, so any fragment the header contains scores 100 before length
        coverage scales it back.
        """
        for fields in seed._ANCHOR_PATTERNS.values():
            for field, anchors in fields.items():
                for anchor in anchors:
                    for header in self.HEADER_LINES:
                        score = similarity(header, anchor)
                        assert score < ANCHOR_THRESHOLD, f"{field}: {anchor!r} → {score}"


class TestGenerationsDiffer:
    """⭐ The two cards are not variants of one layout — §7.4.7."""

    def test_the_expiry_date_is_on_opposite_sides(self, cccd_2021, can_cuoc_2024):
        assert cccd_2021._ZONE_MAP["expiry_date"]["side"] == "FRONT"
        assert can_cuoc_2024._ZONE_MAP["expiry_date"]["side"] == "BACK"

    def test_every_front_field_sits_lower_on_the_2024_card(
        self, cccd_2021, can_cuoc_2024
    ):
        """Reusing the 2021 map would put `full_name` over the number."""
        for field in ("id_number", "full_name", "date_of_birth"):
            assert can_cuoc_2024._ZONE_MAP[field]["y"] > cccd_2021._ZONE_MAP[field]["y"]

    def test_the_mrz_band_is_the_one_thing_that_did_not_move(
        self, cccd_2021, can_cuoc_2024
    ):
        assert can_cuoc_2024._ZONE_MAP["mrz"] == cccd_2021._ZONE_MAP["mrz"]

    def test_the_two_document_codes_are_distinct(self, cccd_2021, can_cuoc_2024):
        assert cccd_2021.CCCD_CHIP_ID != can_cuoc_2024.CAN_CUOC_2024_ID


class TestDateAnchorsDoNotCrossMatch:
    """⭐ The regression this file exists for.

    `Ngày, tháng, năm cấp` and `Ngày, tháng, năm hết hạn` share a long prefix;
    scored in full against each other's real recognized line they reach 83.9 and
    83.3, over the 75 threshold. `_beside_label` returns the FIRST matching
    label in reading order and the issue label is printed first, so
    `expiry_date` would have confidently reported the issue date.
    """

    ISSUE_LINE = "Ngay,thang,namcap/Dateo"
    EXPIRY_LINE = "Nqay,thang, nam het han/Date of expl"

    def test_the_issue_anchor_ignores_the_expiry_label(self, can_cuoc_2024):
        anchors = can_cuoc_2024._ANCHOR_PATTERNS["back"]["issue_date"]
        best = max(similarity(self.EXPIRY_LINE, anchor) for anchor in anchors)
        assert best < ANCHOR_THRESHOLD

    def test_the_expiry_anchor_ignores_the_issue_label(self, can_cuoc_2024):
        anchors = can_cuoc_2024._ANCHOR_PATTERNS["back"]["expiry_date"]
        best = max(similarity(self.ISSUE_LINE, anchor) for anchor in anchors)
        assert best < ANCHOR_THRESHOLD

    @pytest.mark.parametrize(
        ("field", "line"),
        [("issue_date", ISSUE_LINE), ("expiry_date", EXPIRY_LINE)],
    )
    def test_each_anchor_still_matches_its_own_label(
        self, can_cuoc_2024, field, line
    ):
        anchors = can_cuoc_2024._ANCHOR_PATTERNS["back"][field]
        best = max(similarity(line, anchor) for anchor in anchors)
        assert best >= ANCHOR_THRESHOLD
