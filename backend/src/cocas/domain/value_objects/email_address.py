"""EmailAddress value object (§8.3.3)."""
from __future__ import annotations

import re
from dataclasses import dataclass

from cocas.domain.exceptions import ValidationError

_EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9._%+-]*[A-Za-z0-9])?"
    r"@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*"
    r"\.[A-Za-z]{2,63}$"
)
_MAX_LOCAL_LEN = 64
_MAX_TOTAL_LEN = 254

# 🟡 WARNING-only: common domain typos, surfaced as a suggestion — never blocking.
_TYPO_DOMAINS: dict[str, str] = {
    "gmai.com": "gmail.com",
    "gmial.com": "gmail.com",
    "gmail.co": "gmail.com",
    "yaho.com": "yahoo.com",
    "hotmial.com": "hotmail.com",
    "outlok.com": "outlook.com",
}


@dataclass(frozen=True, slots=True)
class EmailAddress:
    """A validated, normalized (trimmed + lowercased) email address."""

    value: str

    def __post_init__(self) -> None:
        if ".." in self.value:
            raise ValidationError(
                "Email không hợp lệ. Ví dụ đúng: ten@example.com",
                code="INVALID_EMAIL",
                field="email",
            )
        local_part = self.value.split("@", 1)[0]
        if len(local_part) > _MAX_LOCAL_LEN or len(self.value) > _MAX_TOTAL_LEN:
            raise ValidationError(
                "Email không hợp lệ. Ví dụ đúng: ten@example.com",
                code="INVALID_EMAIL_LENGTH",
                field="email",
            )
        if not _EMAIL_PATTERN.match(self.value):
            raise ValidationError(
                "Email không hợp lệ. Ví dụ đúng: ten@example.com",
                code="INVALID_EMAIL",
                field="email",
            )

    @classmethod
    def from_raw(cls, raw: str) -> EmailAddress:
        """Trim then lowercase before validating."""
        return cls((raw or "").strip().lower())

    @property
    def domain(self) -> str:
        return self.value.rsplit("@", 1)[1]

    @property
    def typo_suggestion(self) -> str | None:
        """A corrected domain guess for a common typo, or None — 🟡 never blocks."""
        corrected = _TYPO_DOMAINS.get(self.domain)
        if corrected is None:
            return None
        local_part = self.value.split("@", 1)[0]
        return f"{local_part}@{corrected}"

    def __str__(self) -> str:
        return self.value
