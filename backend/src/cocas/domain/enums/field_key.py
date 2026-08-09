"""The 6 extracted CCCD fields (§4.3.3 `FieldKey`, `ocr_field.field_key`)."""
from enum import Enum


class FieldKey(str, Enum):
    """One of the 6 fields extracted from a CCCD by the OCR pipeline."""

    FULL_NAME = "full_name"
    ID_NUMBER = "id_number"
    DATE_OF_BIRTH = "date_of_birth"
    ISSUE_DATE = "issue_date"
    EXPIRY_DATE = "expiry_date"
    ISSUE_PLACE = "issue_place"
