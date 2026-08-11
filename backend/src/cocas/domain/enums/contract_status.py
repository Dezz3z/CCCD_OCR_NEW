"""Contract lifecycle status (§4.3.3 `ContractStatus`, `contract.status`).

⭐ D2.1 — 9 → 6 giá trị. `DOCX_READY`, `PDF_CONVERTING` và `PDF_FAILED` chỉ
mô tả khoảng thời gian giữa "đã có DOCX" và "đã có PDF"; sau khi gỡ khâu
xuất PDF (§9.13) khoảng đó bằng không, nên `GENERATING` đi thẳng tới
`COMPLETED`.
"""
from enum import Enum


class ContractStatus(str, Enum):
    """Contract lifecycle status."""

    DRAFT = "DRAFT"
    GENERATING = "GENERATING"
    COMPLETED = "COMPLETED"
    GENERATION_FAILED = "GENERATION_FAILED"
    SUPERSEDED = "SUPERSEDED"
    VOIDED = "VOIDED"
