"""CitizenId value object — Vietnamese CCCD number (§8.3.1)."""
from __future__ import annotations

import re
from dataclasses import dataclass

from cocas.domain.exceptions import ValidationError

_DIGITS_ONLY = re.compile(r"\D")
_STRUCTURE = re.compile(r"^(?P<province>\d{3})(?P<gender_century>[0-5])(?P<birth_yy>\d{2})(?P<seq>\d{6})$")

# Common OCR misreads, applied only while parsing raw OCR text.
_OCR_DIGIT_FIXUPS = {
    "O": "0",
    "I": "1",
    "L": "1",
    "S": "5",
    "B": "8",
    "Z": "2",
    "G": "6",
    "D": "0",
}

_CENTURY_BY_DIGIT: dict[str, tuple[int, int]] = {
    "0": (1900, 1999),
    "1": (1900, 1999),
    "2": (2000, 2099),
    "3": (2000, 2099),
    "4": (2100, 2199),
    "5": (2100, 2199),
}
_MALE_DIGITS = frozenset("024")
_FEMALE_DIGITS = frozenset("135")


@dataclass(frozen=True, slots=True)
class CitizenId:
    """A validated 12-digit Vietnamese Citizen ID (CCCD) number.

    Only enforces the invariant `^\\d{12}$`. The stronger structural checks
    (province code exists, gender/century digit matches, birth year matches)
    are 🟡 WARNING-level and cross-field, so they are exposed as read-only
    properties for `ValidationEngine` rules (V-OCR-021..023) to consume —
    the VO itself never rejects a syntactically valid 12-digit string based
    on them.
    """

    value: str

    def __post_init__(self) -> None:
        if not (len(self.value) == 12 and self.value.isdigit()):
            raise ValidationError(
                f"Số CCCD phải có đúng 12 chữ số. Hiện có {len(self.value)} chữ số.",
                code="INVALID_CITIZEN_ID_LENGTH",
                field="citizen_id",
                hint="Kiểm tra lại trường 'Số CCCD'. Nếu ảnh mờ, hãy chụp lại mặt trước.",
            )

    @classmethod
    def from_raw(cls, raw: str) -> CitizenId:
        """Strip non-digit characters before validating."""
        return cls(_DIGITS_ONLY.sub("", raw or ""))

    @classmethod
    def from_ocr_text(cls, raw: str) -> CitizenId:
        """Apply common OCR digit misreads (O→0, I/l→1, S→5, ...) then validate."""
        fixed = "".join(_OCR_DIGIT_FIXUPS.get(ch.upper(), ch) for ch in (raw or ""))
        return cls.from_raw(fixed)

    @property
    def _structure(self) -> re.Match[str] | None:
        return _STRUCTURE.match(self.value)

    @property
    def province_code(self) -> str:
        """First 3 digits — province of birth registration."""
        return self.value[0:3]

    @property
    def gender_century_digit(self) -> str:
        """4th digit — encodes gender + century of birth."""
        return self.value[3]

    @property
    def birth_year_suffix(self) -> str:
        """5th-6th digits — last two digits of the birth year."""
        return self.value[4:6]

    @property
    def sequence(self) -> str:
        """Last 6 digits — random sequence, not checked."""
        return self.value[6:12]

    @property
    def inferred_gender(self) -> str | None:
        """"MALE"/"FEMALE" inferred from the gender/century digit parity."""
        digit = self.gender_century_digit
        if digit in _MALE_DIGITS:
            return "MALE"
        if digit in _FEMALE_DIGITS:
            return "FEMALE"
        return None

    @property
    def inferred_birth_year_range(self) -> tuple[int, int] | None:
        """Century range implied by the gender/century digit."""
        return _CENTURY_BY_DIGIT.get(self.gender_century_digit)

    def __str__(self) -> str:
        return self.value
