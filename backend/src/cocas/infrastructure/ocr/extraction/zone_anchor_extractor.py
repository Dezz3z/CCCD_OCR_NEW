"""`IFieldExtractor` (Port 7) — recognized text to the 6 business fields (§7.4.6).

Two strategies run over the same region list and the better result per field
wins:

- **ZONE** — where the field sits on the rectified 1012x638 frame, from
  `document_type.zone_map`. Only meaningful when the perspective warp
  succeeded; on an un-rectified photo those coordinates describe nothing.
- **ANCHOR** — find the printed label, then take the value beside or below it.
  Works on any photo and survives a zone map that has drifted.

⭐ Neither strategy decides what a value *is*. `field_patterns` does, and it is
the gate that keeps a field label, a nationality, or the line above the one we
wanted from being handed to fusion as a citizen id.

⭐ The port takes regions, not an image: recognition already happened at S7 and
must not happen twice — a second whole-card pass would cost more than the rest
of the pipeline put together.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

from cocas.domain.enums.card_side import CardSide
from cocas.domain.enums.field_key import FieldKey
from cocas.domain.ports.ocr import (
    ExtractionStrategy,
    RawFieldValue,
    RelativeBox,
    TextRegion,
)

from . import field_patterns

if TYPE_CHECKING:
    from cocas.domain.ports.ocr import DocumentTypeSpec

# A region counts as "inside" a zone when most of it is; a label that merely
# grazes the box must not be mistaken for the value.
MIN_ZONE_OVERLAP = 0.50

# How far below a label its value may sit, as a multiple of the label's height.
MAX_VALUE_DROP = 2.5

# ⭐ The CCCD number is printed larger than anything else on the front, which
# makes region height a better discriminator than position (§7.4.6).
_TALLEST_WINS = frozenset({FieldKey.ID_NUMBER})

ANCHOR_THRESHOLD = 75.0

_SIDE_KEY = {CardSide.FRONT: "front", CardSide.BACK: "back"}


@dataclass(frozen=True, slots=True)
class _Candidate:
    """One strategy's answer for one field, before the two are compared."""

    value: str
    confidence: float
    bbox: RelativeBox | None
    strategy: ExtractionStrategy


class ZoneAndAnchorExtractor:
    """Map recognized regions onto `FieldKey`s by position and by label."""

    def extract(
        self,
        regions: list[TextRegion],
        side: CardSide,
        doc_type: DocumentTypeSpec,
        warp_succeeded: bool,
    ) -> dict[FieldKey, RawFieldValue]:
        """Return the best value found for each field this side can supply.

        A field with no plausible value is simply absent — an empty string
        would reach fusion as a real reading and outrank nothing at all.
        """
        candidates: dict[FieldKey, list[_Candidate]] = {}

        if warp_succeeded:
            _merge(candidates, self._by_zone(regions, side, doc_type))
        _merge(candidates, self._by_anchor(regions, side, doc_type))

        return {
            key: _to_raw_value(max(found, key=lambda item: item.confidence))
            for key, found in candidates.items()
            if found
        }

    # -- ZONE --------------------------------------------------------------

    def _by_zone(
        self, regions: list[TextRegion], side: CardSide, doc_type: DocumentTypeSpec
    ) -> dict[FieldKey, list[_Candidate]]:
        found: dict[FieldKey, list[_Candidate]] = {}
        for key, zone in _zones_for(side, doc_type).items():
            finder = field_patterns.FINDERS[key]
            for region in sorted(regions, key=lambda item: -_overlap(item.bbox, zone)):
                if _overlap(region.bbox, zone) < MIN_ZONE_OVERLAP:
                    break
                value = finder(region.text)
                if value is not None:
                    found.setdefault(key, []).append(
                        _Candidate(value, region.confidence, region.bbox, ExtractionStrategy.ZONE)
                    )
                    break
        return found

    # -- ANCHOR ------------------------------------------------------------

    def _by_anchor(
        self, regions: list[TextRegion], side: CardSide, doc_type: DocumentTypeSpec
    ) -> dict[FieldKey, list[_Candidate]]:
        found: dict[FieldKey, list[_Candidate]] = {}
        for key, labels in _anchors_for(side, doc_type).items():
            candidate = (
                self._tallest_match(regions, key)
                if key in _TALLEST_WINS
                else None
            ) or self._beside_label(regions, key, labels)
            if candidate is not None:
                found.setdefault(key, []).append(candidate)
        return found

    def _tallest_match(
        self, regions: list[TextRegion], key: FieldKey
    ) -> _Candidate | None:
        """Take the largest-printed region whose text has the right shape.

        ⭐ No label needed: on a CCCD nothing else is printed as large as the
        citizen id, so height alone identifies it even when `Số / No.` was
        never recognized.
        """
        finder = field_patterns.FINDERS[key]
        best: _Candidate | None = None
        best_height = 0.0
        for region in regions:
            value = finder(region.text)
            if value is not None and region.bbox.h > best_height:
                best_height = region.bbox.h
                best = _Candidate(
                    value, region.confidence, region.bbox, ExtractionStrategy.ANCHOR
                )
        return best

    def _beside_label(
        self, regions: list[TextRegion], key: FieldKey, labels: list[str]
    ) -> _Candidate | None:
        """Find the label, then read the value sharing its line or the next one."""
        finder = field_patterns.FINDERS[key]
        for label_region in regions:
            if not field_patterns.looks_like_a_label(
                label_region.text, labels, ANCHOR_THRESHOLD
            ):
                continue
            for region in _reading_order_after(label_region, regions):
                value = finder(region.text)
                if value is not None:
                    return _Candidate(
                        value, region.confidence, region.bbox, ExtractionStrategy.ANCHOR
                    )
        return None


# ============================================================================
# Geometry and configuration helpers
# ============================================================================


def _reading_order_after(
    label: TextRegion, regions: list[TextRegion]
) -> list[TextRegion]:
    """Regions where a label's value can be, nearest first.

    Vietnamese ID cards put the value to the right of its label when it fits
    and on the following line when it does not, so both are searched — the
    same line first, because that is where an unambiguous value sits.
    """
    label_centre = label.bbox.y + label.bbox.h / 2
    same_line: list[TextRegion] = []
    below: list[TextRegion] = []

    for region in regions:
        if region is label:
            continue
        centre = region.bbox.y + region.bbox.h / 2
        if abs(centre - label_centre) <= label.bbox.h * 0.6:
            if region.bbox.x >= label.bbox.x:
                same_line.append(region)
        elif 0 < centre - label_centre <= label.bbox.h * MAX_VALUE_DROP:
            below.append(region)

    same_line.sort(key=lambda item: item.bbox.x)
    below.sort(key=lambda item: (item.bbox.y, item.bbox.x))
    # The label's own line can carry the value after a `:` separator.
    return [label, *same_line, *below]


def _overlap(region: RelativeBox, zone: RelativeBox) -> float:
    """Fraction of `region` lying inside `zone`."""
    width = max(
        0.0, min(region.x + region.w, zone.x + zone.w) - max(region.x, zone.x)
    )
    height = max(
        0.0, min(region.y + region.h, zone.y + zone.h) - max(region.y, zone.y)
    )
    area = region.w * region.h
    return (width * height) / area if area > 0 else 0.0


def _zones_for(side: CardSide, doc_type: DocumentTypeSpec) -> dict[FieldKey, RelativeBox]:
    """The zone-map boxes belonging to this side, as boxes."""
    zones: dict[FieldKey, RelativeBox] = {}
    for name, raw in doc_type.zone_map.items():
        key = _field_key(name)
        if key is None or not isinstance(raw, dict):
            continue
        if raw.get("side") not in (None, side.value):
            continue
        try:
            zones[key] = RelativeBox(
                x=float(raw["x"]), y=float(raw["y"]), w=float(raw["w"]), h=float(raw["h"])
            )
        except (KeyError, TypeError, ValueError):
            logger.warning("Zone {name} of {code} is unusable", name=name, code=doc_type.code)
    return zones


def _anchors_for(side: CardSide, doc_type: DocumentTypeSpec) -> dict[FieldKey, list[str]]:
    """The printed labels for this side, keyed by the field they introduce."""
    section = doc_type.anchor_patterns.get(_SIDE_KEY[side])
    if not isinstance(section, dict):
        return {}

    anchors: dict[FieldKey, list[str]] = {}
    for name, labels in section.items():
        key = _field_key(name)
        if key is not None and isinstance(labels, list):
            anchors[key] = [str(label) for label in labels]
    return anchors


def _field_key(name: str) -> FieldKey | None:
    try:
        return FieldKey(name)
    except ValueError:
        return None  # `mrz` and any future non-field zone


def _merge(
    target: dict[FieldKey, list[_Candidate]], addition: dict[FieldKey, list[_Candidate]]
) -> None:
    for key, values in addition.items():
        target.setdefault(key, []).extend(values)


def _to_raw_value(candidate: _Candidate) -> RawFieldValue:
    return RawFieldValue(
        text=candidate.value,
        confidence=candidate.confidence,
        bbox=candidate.bbox,
        strategy=candidate.strategy,
    )
