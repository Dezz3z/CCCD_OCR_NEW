"""SecuritiesAccountNumber value object (§8.3.5)."""
from __future__ import annotations

import re
from dataclasses import dataclass

from cocas.domain.exceptions import ValidationError

_STRIP_CHARS = re.compile(r"[\s\-]")
_ONLY_SIX_DIGITS = re.compile(r"^\d{6}$")
_GENERAL_PATTERN = re.compile(r"^(?P<member>\d{3})C(?P<customer>\d{6})$")

DEFAULT_MEMBER_CODE = "008"


@dataclass(frozen=True, slots=True)
class SecuritiesAccountNumber:
    """A validated securities trading account number, e.g. `008C123456`.

    ⭐ Rendered into documents **bold** — see `RenderContextBuilder` /
    `DocxContextAdapter`, which wrap this VO's `.value` in a `StyledValue`.
    """

    value: str

    def __post_init__(self) -> None:
        match = _GENERAL_PATTERN.match(self.value)
        if not match:
            raise ValidationError(
                "Số tài khoản chứng khoán phải có dạng 008C theo sau 6 chữ số. "
                "Ví dụ: 008C123456",
                code="INVALID_SECURITIES_ACCOUNT",
                field="securities_account_no",
            )

    @classmethod
    def from_raw(
        cls,
        raw: str,
        *,
        member_code: str = DEFAULT_MEMBER_CODE,
        strict: bool = True,
    ) -> SecuritiesAccountNumber:
        """Strip separators, uppercase, and auto-prefix a bare 6-digit customer number."""
        cleaned = _STRIP_CHARS.sub("", raw or "").upper()
        if _ONLY_SIX_DIGITS.match(cleaned):
            cleaned = f"{member_code}C{cleaned}"
        instance = cls(cleaned)
        if strict and instance.member_code != member_code:
            raise ValidationError(
                "Số tài khoản chứng khoán phải có dạng 008C theo sau 6 chữ số. "
                "Ví dụ: 008C123456",
                code="INVALID_MEMBER_CODE",
                field="securities_account_no",
            )
        return instance

    @property
    def member_code(self) -> str:
        return self.value[0:3]

    @property
    def customer_code(self) -> str:
        return self.value[4:10]

    @property
    def display(self) -> str:
        """Grouped for on-screen readability: `008C 123456`."""
        return f"{self.value[0:4]} {self.value[4:10]}"

    def __str__(self) -> str:
        return self.value
