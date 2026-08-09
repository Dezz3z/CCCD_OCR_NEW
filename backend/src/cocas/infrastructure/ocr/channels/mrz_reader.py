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
from typing import TYPE_CHECKING

from loguru import logger

from cocas.domain.enums.field_key import FieldKey
from cocas.domain.ports.ocr import MrzExtractionResult, RelativeBox

from . import td1

if TYPE_CHECKING:
    from cocas.domain.ports.ocr import (
        DocumentTypeSpec,
        IRegionRecognizer,
        PreprocessedImageSet,
    )

MRZ_CHARSET_HINT = "A-Z0-9<"

# §7.4.6 zone map default for the 1012x638 card frame; overridden per document
# type once the zone map has been calibrated against real cards.
_DEFAULT_BAND = RelativeBox(x=0.02, y=0.82, w=0.96, h=0.16)

# Wider fallback for un-warped images, where the band sits less predictably.
_FALLBACK_BAND = RelativeBox(x=0.0, y=0.75, w=1.0, h=0.25)

CONFIDENCE_CLEAN = 0.98
CONFIDENCE_REPAIRED = 0.90
CONFIDENCE_FAILED = 0.50

_CENTURY = 100


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
        """
        if not doc_type.has_mrz:
            return MrzExtractionResult(available=False)

        band = _band_for(image_set, doc_type)
        try:
            region = self._recognizer.recognize_region(
                image_set.v4, band, MRZ_CHARSET_HINT
            )
        except Exception:
            logger.opt(exception=True).warning("MRZ region recognition failed")
            return MrzExtractionResult(available=False)

        if region is None or not region.text.strip():
            return MrzExtractionResult(available=False)

        lines = td1.normalize_lines(region.text)
        parsed = td1.parse(lines)

        if not parsed.checksum_valid:
            logger.warning(
                "MRZ checksum did not validate after {corrections} correction(s)",
                corrections=parsed.corrections_applied,
                mrz_raw="\n".join(parsed.lines),
            )

        return MrzExtractionResult(
            available=True,
            raw_lines=parsed.lines,
            fields=_to_fields(parsed.fields),
            checksum_valid=parsed.checksum_valid,
            corrections_applied=parsed.corrections_applied,
            confidence=_confidence_for(parsed),
        )


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


def _confidence_for(parsed: td1.Td1Parse) -> float:
    if not parsed.checksum_valid:
        return CONFIDENCE_FAILED
    return CONFIDENCE_REPAIRED if parsed.corrections_applied else CONFIDENCE_CLEAN


def _to_fields(fields: td1.Td1Fields) -> dict[FieldKey, str]:
    """Map TD1 values onto the business fields MRZ can vouch for.

    ⭐ Dates are emitted as `ddmmyyyy` — the same shape the QR channel produces —
    so fusion's consensus rule compares like with like instead of scoring two
    correct readings as a conflict.
    """
    mapped: dict[FieldKey, str] = {}
    if fields.citizen_id:
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
