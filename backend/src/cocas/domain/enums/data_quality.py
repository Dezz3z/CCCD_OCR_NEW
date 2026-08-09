"""Provenance of a customer record's data (§4.3.3 `DataQuality`, `customer.data_quality`)."""
from enum import Enum


class DataQuality(str, Enum):
    """How a customer's data was populated."""

    OCR_VERIFIED = "OCR_VERIFIED"
    MANUAL = "MANUAL"
    MIXED = "MIXED"
