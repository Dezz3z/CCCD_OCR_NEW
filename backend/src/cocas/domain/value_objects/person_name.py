"""PersonName value object — Vietnamese full name (§8.3.6)."""
from __future__ import annotations

from dataclasses import dataclass

from cocas.domain.exceptions import ValidationError
from cocas.domain.value_objects._vn_text import collapse_whitespace, is_vn_name_char, nfc_upper

MIN_LENGTH = 2
MAX_LENGTH = 100

# A Vietnamese full name is a family name plus at least a given name. Fewer
# words is 🟡 (V-OCR-004), never a construction error — see the class docstring.
MIN_WORD_COUNT = 2

# Applied only when the digit sits between two letters — an OCR misread, not
# a legitimate character in a Vietnamese name.
_DIGIT_TO_LETTER = {"0": "O", "1": "I", "5": "S", "8": "B"}


def fix_ocr_digits(text: str) -> str:
    """Turn `0/1/5/8` back into letters, but only between two letters.

    ⭐ Exposed separately from `from_ocr_text` because `FieldNormalizer` has to
    run this step *before* it drops out-of-charset characters (§03 S9 orders
    them that way): strip first and `H0ANG` loses its `0` and becomes `HANG`
    instead of `HOANG`.
    """
    chars = list(text)
    for i, ch in enumerate(chars):
        fixed = _DIGIT_TO_LETTER.get(ch)
        if fixed is None:
            continue
        left = chars[i - 1] if i > 0 else ""
        right = chars[i + 1] if i + 1 < len(chars) else ""
        if left.isalpha() and right.isalpha():
            chars[i] = fixed
    return "".join(chars)


@dataclass(frozen=True, slots=True)
class PersonName:
    """A validated Vietnamese full name, normalized to NFC uppercase.

    ⭐ Word-count < 2 is a 🟡 WARNING (§8.3.6), not a construction error —
    exposed via `word_count` for `ValidationEngine` (V-OCR-004) to decide.
    """

    value: str

    def __post_init__(self) -> None:
        length = len(self.value)
        if not (MIN_LENGTH <= length <= MAX_LENGTH):
            raise ValidationError(
                "Họ và tên chỉ được chứa chữ cái tiếng Việt và khoảng trắng.",
                code="INVALID_NAME_LENGTH",
                field="full_name",
            )
        if any(not is_vn_name_char(ch) for ch in self.value):
            raise ValidationError(
                "Họ và tên chỉ được chứa chữ cái tiếng Việt và khoảng trắng.",
                code="INVALID_CHARACTER",
                field="full_name",
            )

    @classmethod
    def from_raw(cls, raw: str) -> PersonName:
        """NFC-normalize, uppercase, collapse whitespace, trim."""
        return cls(collapse_whitespace(nfc_upper(raw or "")))

    @classmethod
    def from_ocr_text(cls, raw: str) -> PersonName:
        """Like `from_raw`, but first fixes digits misread between letters."""
        return cls(fix_ocr_digits(collapse_whitespace(nfc_upper(raw or ""))))

    @property
    def word_count(self) -> int:
        return len(self.value.split())

    def __str__(self) -> str:
        return self.value
