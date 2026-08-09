"""VietnamesePhone value object (§8.3.2)."""
from __future__ import annotations

import re
from dataclasses import dataclass

from cocas.domain.exceptions import ValidationError

_STRIP_CHARS = re.compile(r"[\s.\-()]")
_LEADING_COUNTRY_CODE = re.compile(r"^\+?84")
_MOBILE_PATTERN = re.compile(r"^0(3[2-9]|5[2689]|7[06-9]|8[1-9]|9[0-9])\d{7}$")

_CARRIER_PREFIXES: dict[str, tuple[str, ...]] = {
    "Viettel": ("032", "033", "034", "035", "036", "037", "038", "039", "086", "096", "097", "098"),
    "Vinaphone": ("081", "082", "083", "084", "085", "088", "091", "094"),
    "Mobifone": ("070", "076", "077", "078", "079", "089", "090", "093"),
    "Vietnamobile": ("052", "056", "058", "092"),
    "Gmobile": ("059", "099"),
    "Itelecom": ("087",),
}


@dataclass(frozen=True, slots=True)
class VietnamesePhone:
    """A normalized Vietnamese mobile phone number, always stored as `0xxxxxxxxx`."""

    value: str

    def __post_init__(self) -> None:
        if not _MOBILE_PATTERN.match(self.value):
            raise ValidationError(
                "Số điện thoại không hợp lệ. Cần 10 chữ số bắt đầu bằng 03, 05, 07, 08 hoặc 09.",
                code="INVALID_PHONE_FORMAT",
                field="phone",
            )

    @classmethod
    def from_raw(cls, raw: str) -> VietnamesePhone:
        """Strip separators and normalize a leading `+84`/`84` to `0`."""
        stripped = _STRIP_CHARS.sub("", raw or "")
        normalized = _LEADING_COUNTRY_CODE.sub("0", stripped)
        return cls(normalized)

    @property
    def carrier(self) -> str | None:
        """Known mobile carrier name, or None if the prefix is unrecognized."""
        prefix = self.value[:3]
        for carrier, prefixes in _CARRIER_PREFIXES.items():
            if prefix in prefixes:
                return carrier
        return None

    def __str__(self) -> str:
        return self.value
