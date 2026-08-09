"""Winning source of a fused OCR field (§4.3.3 `FieldSource`, `ocr_field.source`)."""
from enum import Enum


class FieldSource(str, Enum):
    """Which channel a field's final value came from."""

    QR = "QR"
    MRZ = "MRZ"
    OCR = "OCR"
    MANUAL = "MANUAL"
    NONE = "NONE"
