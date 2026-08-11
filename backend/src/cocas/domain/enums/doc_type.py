"""Generated document type (§4.3.3 `DocType`, `contract_document.doc_type`).

⭐ D2.1 — chỉ còn `DOCX`. Cột `doc_type` vẫn tồn tại vì
`uq_contract_document__type` là thứ chặn ghi hai bản ghi tài liệu cho cùng
một hợp đồng; và một enum một-giá-trị là chỗ đúng để thêm định dạng mới
nếu sau này cần.
"""
from enum import Enum


class DocType(str, Enum):
    """The file format of a generated contract document."""

    DOCX = "DOCX"
