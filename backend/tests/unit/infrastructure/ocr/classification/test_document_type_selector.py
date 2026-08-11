"""Tests for `MarkerDocumentTypeSelector` (Port 19) — §7.4.7.

⭐ Half of these test the **seeded markers**, not the code. The selector is nine
lines of counting; what can actually go wrong is somebody adding a marker that
both generations print, which is the exact mistake §7.4.7 records being made
with `CĂN CƯỚC` and `IDENTITY CARD`. So the data gets checked too, straight out
of the migration, the way `test_doctype_seeds.py` does.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from cocas.domain.ports.ocr import DocumentTypeSpec, RelativeBox, TextRegion
from cocas.infrastructure.ocr.classification.document_type_selector import (
    MARKER_THRESHOLD,
    MarkerDocumentTypeSelector,
)
from cocas.infrastructure.ocr.text_matching import similarity

_VERSIONS = Path(__file__).resolve().parents[5] / "migrations" / "versions"


def _load(filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(filename, _VERSIONS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def seeded_markers() -> dict[str, list[str]]:
    """The real lists, from the migration that writes them."""
    return _load("20260811_010_markers_tier5.py")._MARKERS


def spec(code: str, markers: list[str]) -> DocumentTypeSpec:
    return DocumentTypeSpec(
        code=code,
        name=code,
        field_schema=[],
        zone_map={},
        anchor_patterns={},
        has_qr=True,
        has_mrz=True,
        is_ocr_supported=True,
        expected_aspect_ratio=1.585,
        identity_markers=tuple(markers),
    )


@pytest.fixture
def both(seeded_markers: dict[str, list[str]]) -> list[DocumentTypeSpec]:
    return [
        spec("CCCD_CHIP", seeded_markers["CCCD_CHIP"]),
        spec("CAN_CUOC_2024", seeded_markers["CAN_CUOC_2024"]),
    ]


def lines(*texts: str) -> list[TextRegion]:
    return [
        TextRegion(bbox=RelativeBox(x=0.0, y=0.1 * i, w=1.0, h=0.05), text=text, confidence=0.9)
        for i, text in enumerate(texts)
    ]


# ⭐ Written the way the recognizer actually emits them: diacritics gone, words
# run together (§7.4.6 — real cards produced `CONG HOAXAHOI CHU NGHIAVIET NAM`).
# Comparing against clean strings would test a recognizer nobody has.
FRONT_2021 = lines(
    "CONG HOA XA HOI CHU NGHIAVIET NAM",
    "CAN CUOC CONG DAN",
    "Citizen Identity Card",
    "Ho va ten: NGUYEN VAN AN",
)
BACK_2021 = lines(
    "DAC DIEM NHAN DANG",
    "Que quan: Ha Noi",
    "Noi thuong tru: 12 Pho Hue",
    "CUCTRUONG CUCCANH SAT",
)
FRONT_2024 = lines(
    "CONG HOA XA HOI CHU NGHIA VIET NAM",
    "CAN CUOC",
    "So dinh danh ca nhan",
    "Noi dang ky khai sinh: Ha Noi",
)
BACK_2024 = lines("Noi cu tru: 12 Pho Hue", "BO CONGAN", "Ngay thang nam het han")


class TestRealisticReadings:
    def test_a_2021_front_is_recognized_as_the_2021_generation(self, both) -> None:
        assert MarkerDocumentTypeSelector().select(FRONT_2021, both).code == "CCCD_CHIP"

    def test_a_2021_back_is_recognized_as_the_2021_generation(self, both) -> None:
        assert MarkerDocumentTypeSelector().select(BACK_2021, both).code == "CCCD_CHIP"

    def test_a_2024_front_is_recognized_as_the_2024_generation(self, both) -> None:
        assert MarkerDocumentTypeSelector().select(FRONT_2024, both).code == "CAN_CUOC_2024"

    def test_a_2024_back_is_recognized_as_the_2024_generation(self, both) -> None:
        assert MarkerDocumentTypeSelector().select(BACK_2024, both).code == "CAN_CUOC_2024"

    def test_both_sides_together_agree_with_each_side_alone(self, both) -> None:
        """The pipeline pools regions from both photos before asking."""
        selector = MarkerDocumentTypeSelector()
        assert selector.select(FRONT_2021 + BACK_2021, both).code == "CCCD_CHIP"
        assert selector.select(FRONT_2024 + BACK_2024, both).code == "CAN_CUOC_2024"


class TestRefusingToGuess:
    """⭐ `None` means "keep what the session declared" — the safe answer."""

    def test_no_regions_means_no_verdict(self, both) -> None:
        assert MarkerDocumentTypeSelector().select([], both) is None

    def test_blank_regions_mean_no_verdict(self, both) -> None:
        assert MarkerDocumentTypeSelector().select(lines("   ", ""), both) is None

    def test_text_matching_neither_generation_means_no_verdict(self, both) -> None:
        assert MarkerDocumentTypeSelector().select(lines("HELLO WORLD", "12345"), both) is None

    def test_a_tie_means_no_verdict_rather_than_the_first_listed(self, both) -> None:
        """Breaking ties by order would turn "no evidence" into a silent vote."""
        tied = lines("Que quan: Ha Noi", "Noi cu tru: 12 Pho Hue")
        assert MarkerDocumentTypeSelector().select(tied, both) is None

    def test_shared_boilerplate_alone_decides_nothing(self, both) -> None:
        """⚠️ The republic header is on every card of both generations."""
        shared = lines("CONG HOA XA HOI CHU NGHIA VIET NAM", "Doc lap - Tu do - Hanh phuc")
        assert MarkerDocumentTypeSelector().select(shared, both) is None

    def test_a_single_candidate_is_returned_without_looking_at_the_text(self, both) -> None:
        only = [both[0]]
        assert MarkerDocumentTypeSelector().select([], only) is only[0]

    def test_no_candidates_yields_none(self) -> None:
        assert MarkerDocumentTypeSelector().select(FRONT_2021, []) is None

    def test_a_type_with_no_markers_never_wins(self, seeded_markers) -> None:
        candidates = [
            spec("CCCD_CHIP", seeded_markers["CCCD_CHIP"]),
            spec("MYSTERY", []),
        ]
        assert MarkerDocumentTypeSelector().select(FRONT_2021, candidates).code == "CCCD_CHIP"


class TestSeededMarkers:
    """The data. This is the half that catches a future edit."""

    def test_both_generations_have_markers(self, seeded_markers) -> None:
        assert set(seeded_markers) == {"CCCD_CHIP", "CAN_CUOC_2024"}
        assert all(markers for markers in seeded_markers.values())

    def test_no_marker_of_one_generation_matches_a_marker_of_the_other(
        self, seeded_markers
    ) -> None:
        """⭐ The check that would have caught `CĂN CƯỚC` vs `CĂN CƯỚC CÔNG DÂN`,
        which score 100 against each other and tie the vote on every 2021 front."""
        collisions = [
            (a, b)
            for a in seeded_markers["CCCD_CHIP"]
            for b in seeded_markers["CAN_CUOC_2024"]
            if similarity(a, b) >= MARKER_THRESHOLD or similarity(b, a) >= MARKER_THRESHOLD
        ]
        assert collisions == []

    def test_the_titles_that_were_measured_to_collide_are_still_absent(
        self, seeded_markers
    ) -> None:
        """A regression guard on a specific removal, not on the rule in general."""
        every = [m for markers in seeded_markers.values() for m in markers]
        assert "CĂN CƯỚC" not in every
        assert "IDENTITY CARD" not in every

    def test_no_marker_matches_the_republic_header_both_cards_print(
        self, seeded_markers
    ) -> None:
        header = "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM"
        for markers in seeded_markers.values():
            for marker in markers:
                assert similarity(header, marker) < MARKER_THRESHOLD, marker

    def test_markers_are_long_enough_to_mean_something(self, seeded_markers) -> None:
        """⚠️ CLAUDE.md constraint 7: `Số` (2 chars) scored 100 against
        `SOCIALIST REPUBLIC`, and `Số:` (3) reached 80.

        ⭐ 6 is where the seed actually sits — `Quê quán` compacts to 7 and is
        the shortest surviving marker — not a round number. `similarity` scales
        by coverage only when the *text* is short, so a short marker found
        inside a long line pays no penalty at all; length is the only guard
        there is.
        """
        for markers in seeded_markers.values():
            for marker in markers:
                assert len(marker.replace(" ", "")) >= 6, marker
