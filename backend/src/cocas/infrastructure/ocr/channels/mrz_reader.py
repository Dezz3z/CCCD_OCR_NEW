"""`IMrzReader` (Port 6) production implementation — §7.4.4.

⭐ Depends on `IRegionRecognizer`, not `IOcrEngine` (ISP, §7.3): the MRZ channel
only ever needs "read the text inside this box", so it stays usable with any
recognizer — including the fake one in tests, which is how this module is
verified before a real engine exists in week 3.

⭐ Never raises. An unreadable MRZ is reported as `available=False`, matching
the QR channel: the card is still usable through OCR plus manual entry (P-08).
"""
from __future__ import annotations

from datetime import date
from operator import attrgetter
from typing import TYPE_CHECKING

from loguru import logger

from cocas.domain.enums.field_key import FieldKey
from cocas.domain.ports.ocr import MrzExtractionResult, RelativeBox

from . import td1

if TYPE_CHECKING:
    from cocas.domain.ports.ocr import (
        DocumentTypeSpec,
        ImageData,
        IRegionRecognizer,
        PreprocessedImageSet,
    )

MRZ_CHARSET_HINT = "A-Z0-9<"

# ⭐ Measured, not assumed. Across 20 real backs the block spans y=0.661..0.933
# of the rectified frame; the design's original 0.82..0.98 band sat below the
# first two lines and read the address block instead. The band is deliberately
# generous now — `td1.select_lines` decides what is MRZ, not the coordinates.
_DEFAULT_BAND = RelativeBox(x=0.02, y=0.62, w=0.96, h=0.36)

# Wider still for un-warped images, where the block sits less predictably.
_FALLBACK_BAND = RelativeBox(x=0.0, y=0.55, w=1.0, h=0.45)

CONFIDENCE_CLEAN = 0.98
CONFIDENCE_REPAIRED = 0.90
CONFIDENCE_FAILED = 0.50

_CENTURY = 100
CITIZEN_ID_LENGTH = 12


class Td1MrzReader:
    """Locate, read, and checksum-validate the TD1 MRZ block on the card back."""

    def __init__(self, recognizer: IRegionRecognizer) -> None:
        self._recognizer = recognizer

    def read(
        self,
        image_set: PreprocessedImageSet,
        doc_type: DocumentTypeSpec,
    ) -> MrzExtractionResult:
        """Read the MRZ band and report both its values and its trustworthiness.

        `checksum_valid=False` is a deliberate outcome, not an error: the values
        are still returned so fusion can weigh them against the other channels.

        ⭐ Tries `v3` before `v4`, stopping at the first block whose checksums
        pass. The design named `v4` (binarized) as *the* MRZ variant on the
        reasoning that MRZ is monospaced black-on-white; measured on 20 real
        backs, adaptive thresholding thins the strokes enough to cost 8 of the
        20 blocks outright. `v4` stays as the fallback because it still wins on
        the low-contrast shots that `v3` loses.
        """
        if not doc_type.has_mrz:
            return MrzExtractionResult(available=False)

        band = _band_for(image_set, doc_type)
        best: td1.Td1Parse | None = None

        # ⭐ `attrgetter`, not `(image_set.v3, image_set.v4)` — building that
        # tuple would materialize BOTH variants before the first is even tried,
        # quietly undoing the lazy variant set (§7.4.1).
        for accessor in (attrgetter("v3"), attrgetter("v4")):
            parsed = self._read_variant(accessor(image_set), band)
            if parsed is None:
                continue
            if parsed.checksum_valid:
                return _result_for(parsed)
            if best is None:
                best = parsed

        if best is None:
            return MrzExtractionResult(available=False)

        logger.warning(
            "MRZ checksum did not validate after {corrections} correction(s)",
            corrections=best.corrections_applied,
            mrz_raw="\n".join(best.lines),
        )
        return _result_for(best)

    def _read_variant(self, image: ImageData, band: RelativeBox) -> td1.Td1Parse | None:
        """Recognize one variant's band and parse it, or None if it yielded no block."""
        try:
            region = self._recognizer.recognize_region(image, band, MRZ_CHARSET_HINT)
        except Exception:
            logger.opt(exception=True).warning("MRZ region recognition failed")
            return None

        if region is None or not region.text.strip():
            return None

        lines = td1.select_lines(region.text)
        if lines is None:
            return None
        return td1.parse(lines)


def _band_for(
    image_set: PreprocessedImageSet, doc_type: DocumentTypeSpec
) -> RelativeBox:
    """⭐ Use the calibrated zone only when the card was actually rectified.

    On an un-warped image the zone map's coordinates mean nothing, so a wider
    band is scanned instead of trusting numbers that no longer apply.
    """
    if not image_set.warp_succeeded:
        return _FALLBACK_BAND
    zone = doc_type.zone_map.get("mrz")
    if not isinstance(zone, dict):
        return _DEFAULT_BAND
    try:
        return RelativeBox(
            x=float(zone["x"]), y=float(zone["y"]), w=float(zone["w"]), h=float(zone["h"])
        )
    except (KeyError, TypeError, ValueError):
        logger.warning("Document type {code} has an unusable MRZ zone", code=doc_type.code)
        return _DEFAULT_BAND


def _result_for(parsed: td1.Td1Parse) -> MrzExtractionResult:
    return MrzExtractionResult(
        available=True,
        raw_lines=parsed.lines,
        fields=_to_fields(parsed.fields),
        checksum_valid=parsed.checksum_valid,
        corrections_applied=parsed.corrections_applied,
        confidence=_confidence_for(parsed),
    )


def _confidence_for(parsed: td1.Td1Parse) -> float:
    """§7.4.4 step 8 — clean 0.98, repaired 0.90, never-valid 0.50.

    ⭐ The composite check decides "clean" rather than "valid": a block whose
    four field checks pass but whose whole-block digit did not survive the
    filler run is trustworthy, just not pristine.
    """
    if not parsed.checksum_valid:
        return CONFIDENCE_FAILED
    if parsed.corrections_applied or not parsed.composite_valid:
        return CONFIDENCE_REPAIRED
    return CONFIDENCE_CLEAN


def _to_fields(fields: td1.Td1Fields) -> dict[FieldKey, str]:
    """Map TD1 values onto the business fields MRZ can vouch for.

    ⭐ Dates are emitted as `ddmmyyyy` — the same shape the QR channel produces —
    so fusion's consensus rule compares like with like instead of scoring two
    correct readings as a conflict.

    ⭐ Every value is shape-checked before it leaves. A block that failed its
    checksums still reaches fusion at confidence 0.50, so anything that is not
    a well-formed value must be dropped here rather than counted against the
    0.5% False Confidence budget.
    """
    mapped: dict[FieldKey, str] = {}
    if len(fields.citizen_id) == CITIZEN_ID_LENGTH and fields.citizen_id.isdigit():
        mapped[FieldKey.ID_NUMBER] = fields.citizen_id
    birth = _to_ddmmyyyy(fields.date_of_birth, is_expiry=False)
    if birth:
        mapped[FieldKey.DATE_OF_BIRTH] = birth
    expiry = _to_ddmmyyyy(fields.date_of_expiry, is_expiry=True)
    if expiry:
        mapped[FieldKey.EXPIRY_DATE] = expiry
    return mapped


def _to_ddmmyyyy(yymmdd: str, *, is_expiry: bool) -> str | None:
    """Expand a 6-digit MRZ date, or None when it is not a usable date.

    ⭐ Expiry always resolves to the 2000s: a card cannot have expired before
    the CCCD scheme existed. Birth years use the "not in the future" rule.
    """
    if len(yymmdd) != 6 or not yymmdd.isdigit():
        return None
    year_pair, month, day = int(yymmdd[0:2]), yymmdd[2:4], yymmdd[4:6]
    if not (1 <= int(month) <= 12 and 1 <= int(day) <= 31):
        return None

    if is_expiry:
        year = 2000 + year_pair
    else:
        current_pair = date.today().year % _CENTURY
        year = 2000 + year_pair if year_pair <= current_pair else 1900 + year_pair
    return f"{day}{month}{year}"
