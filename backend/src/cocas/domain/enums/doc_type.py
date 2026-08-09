"""Generated document type (§4.3.3 `DocType`, `contract_document.doc_type`)."""
from enum import Enum


class DocType(str, Enum):
    """The file format of a generated contract document."""

    DOCX = "DOCX"
    PDF = "PDF"
