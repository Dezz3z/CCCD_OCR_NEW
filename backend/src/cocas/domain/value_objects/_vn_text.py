"""Shared Vietnamese-text helpers for value objects.

⭐ Private module — not part of the public `value_objects` API.

Per docs/design/CLAUDE.md pitfall #2: the Unicode range `À-Ỹ` must NEVER be
used for Vietnamese uppercase matching (it includes lowercase letters and
non-Vietnamese glyphs). Instead we use an explicit character set, built from
the literal table in docs/design/08-validation.md §8.3.6.
"""
import unicodedata

# Explicit uppercase Vietnamese alphabet (base Latin + Vietnamese-specific
# base letters + every precomposed tone-marked vowel used in Vietnamese).
_VN_UPPERCASE_LETTERS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "ĂÂĐÊÔƠƯ"
    "ÀÁẢÃẠẰẮẲẴẶẦẤẨẪẬ"
    "ÈÉẺẼẸỀẾỂỄỆ"
    "ÌÍỈĨỊ"
    "ÒÓỎÕỌỒỐỔỖỘỜỚỞỠỢ"
    "ÙÚỦŨỤỪỨỬỮỰ"
    "ỲÝỶỸỴ"
)

# Extra characters permitted in a person's name besides letters.
_VN_NAME_EXTRA_CHARS = frozenset(" -'")


def nfc_upper(raw: str) -> str:
    """Unicode NFC normalize FIRST, then uppercase.

    ⭐ Order matters: NFC-then-uppercase gives identical results for both
    NFC and NFD input, which is a mandatory test case (§8.3.6).
    """
    return unicodedata.normalize("NFC", raw).upper()


def collapse_whitespace(raw: str) -> str:
    """Collapse runs of whitespace to a single space and trim."""
    return " ".join(raw.split())


def is_vn_uppercase_letter(ch: str) -> bool:
    """True if `ch` is one of the 89 explicit Vietnamese uppercase letters."""
    return ch in _VN_UPPERCASE_LETTERS


def is_vn_name_char(ch: str) -> bool:
    """True if `ch` is a letter or one of the extra name characters (§8.3.6)."""
    return ch in _VN_UPPERCASE_LETTERS or ch in _VN_NAME_EXTRA_CHARS


def strip_diacritics(text: str) -> str:
    """NFD-decompose, drop combining marks, then fold Đ/đ → D.

    Đ/đ (U+0110/U+0111) don't decompose under NFD — they're their own base
    letters, not a letter+mark pair — so they need an explicit fold. Used
    both for `normalization_alias.alias_normalized`-style matching and for
    `export.strip_diacritics` filename generation.
    """
    decomposed = unicodedata.normalize("NFD", text)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    without_dj = without_marks.replace("Đ", "D").replace("đ", "d")
    return unicodedata.normalize("NFC", without_dj)
