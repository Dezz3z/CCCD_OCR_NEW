"""IssuePlace value object (§8.3.9).

⭐ One of three enforcement layers for this field, together with the
Pydantic `Literal` at the API boundary and the `CHECK` constraint in the
database. This is the ⭐ source-of-truth layer.
"""
from __future__ import annotations

from dataclasses import dataclass

from cocas.domain.exceptions import ValidationError
from cocas.domain.value_objects._vn_text import collapse_whitespace, nfc_upper

BO_CONG_AN = "BỘ CÔNG AN"
CUC_CANH_SAT_QLHC_TTXH = "CỤC CẢNH SÁT QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI"

ALLOWED_VALUES: frozenset[str] = frozenset({BO_CONG_AN, CUC_CANH_SAT_QLHC_TTXH})


@dataclass(frozen=True, slots=True)
class IssuePlace:
    """The CCCD issuing authority — exactly one of two canonical values.

    This VO performs an exact whitelist match only. Fuzzy/alias resolution
    of raw OCR text into one of the two canonical strings is the job of the
    `IssuePlaceNormalizer` domain service, which is expected to hand this
    VO an already-normalized string (or `None`, in which case no `IssuePlace`
    is constructed at all).
    """

    value: str

    def __post_init__(self) -> None:
        if self.value not in ALLOWED_VALUES:
            raise ValidationError(
                "Nơi cấp phải là một trong hai giá trị chuẩn.",
                code="ISSUE_PLACE_UNRECOGNIZED",
                field="issue_place",
            )

    @classmethod
    def from_exact_text(cls, raw: str) -> IssuePlace:
        """NFC-normalize, uppercase, and collapse whitespace before matching."""
        return cls(collapse_whitespace(nfc_upper(raw or "")))

    def __str__(self) -> str:
        return self.value
