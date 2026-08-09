"""Contract lifecycle status (§4.3.3 `ContractStatus`, `contract.status`)."""
from enum import Enum


class ContractStatus(str, Enum):
    """Contract lifecycle status."""

    DRAFT = "DRAFT"
    GENERATING = "GENERATING"
    DOCX_READY = "DOCX_READY"
    PDF_CONVERTING = "PDF_CONVERTING"
    COMPLETED = "COMPLETED"
    GENERATION_FAILED = "GENERATION_FAILED"
    PDF_FAILED = "PDF_FAILED"
    SUPERSEDED = "SUPERSEDED"
    VOIDED = "VOIDED"
