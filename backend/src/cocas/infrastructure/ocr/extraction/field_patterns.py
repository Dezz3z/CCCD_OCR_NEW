"""What each of the 6 fields looks like once recognized — §7.4.6 value rules.

⭐ Shape recognition is what makes both extraction strategies work. ZONE says
*where* to look and ANCHOR says *next to what*, but neither can tell a date from
a document number; the patterns here are what turn a nearby line of text into a
value worth keeping. They are also the last filter before a value reaches
fusion, so a pattern that matches too loosely spends the False Confidence
budget directly.

Every function is pure and takes recognized text, so the whole set is testable
without an image, an engine, or a card.
"""
from __future__ import annotations

import re

from cocas.domain.enums.field_key import FieldKey

from ..text_matching import is_printed_boilerplate, matches_any, similarity

# `13/03/1987`, tolerating the spaces a recognizer inserts around separators
# and the `.`/`-` it substitutes for `/`.
_DATE = re.compile(r"(\d{2})\s*[/.\-]\s*(\d{2})\s*[/.\-]\s*(\d{4})")

# The CCCD number: exactly 12 digits, not part of a longer run.
_ID_NUMBER = re.compile(r"(?<!\d)(\d{12})(?!\d)")

# Cards issued without an expiry print this instead of a date.
NO_EXPIRY = "KHÔNG THỜI HẠN"
# ⭐ 85, not the 80 used elsewhere: a garbled `ovong thoi hg` from an unrelated
# part of a real card scored exactly 80 against this phrase. A short fuzzy
# anchor is the easiest way to spend the False Confidence budget.
_NO_EXPIRY_THRESHOLD = 85.0


# A name line is letters and spaces only — no digits, no punctuation beyond the
# apostrophe the recognizer emits for the horn diacritic.
_NAME_LINE = re.compile(r"^[A-Za-zÀ-ỹ' ]{4,}$")

# Labels sit on the same line as their value often enough that the label text
# has to be stripped before the value can be read.
_LABEL_TAIL = re.compile(r"^.*?[:;]\s*")

MIN_NAME_WORDS = 2


def find_id_number(text: str) -> str | None:
    """The 12-digit citizen id, if this text carries one."""
    match = _ID_NUMBER.search(_digits_only_spacing(text))
    return match.group(1) if match else None


def find_date(text: str) -> str | None:
    """A `dd/mm/yyyy` date, normalized to that exact shape.

    ⭐ Returned with slashes regardless of what the recognizer produced, so the
    validation layer sees one format and fusion compares like with like.
    """
    match = _DATE.search(text)
    if match is None:
        return None
    day, month, year = match.groups()
    if not (1 <= int(day) <= 31 and 1 <= int(month) <= 12):
        return None
    return f"{day}/{month}/{year}"


def find_expiry(text: str) -> str | None:
    """A date, or the words a card without an expiry prints instead."""
    date = find_date(text)
    if date is not None:
        return date
    if similarity(text, NO_EXPIRY) >= _NO_EXPIRY_THRESHOLD:
        return NO_EXPIRY
    return None


def find_name(text: str) -> str | None:
    """A person's name: at least two alphabetic words, no digits.

    ⚠️ Returned as recognized — usually **without diacritics**, because
    `lang='vi'` resolves to the latin model. The value is still worth having:
    fusion compares it against the QR name folded the same way, and a user
    correcting an unaccented name is a much smaller task than typing one.
    """
    candidate = _strip_label(text).strip()
    if not _NAME_LINE.match(candidate):
        return None
    if len(candidate.split()) < MIN_NAME_WORDS:
        return None
    if is_printed_boilerplate(candidate):
        return None
    return " ".join(candidate.split()).upper()


def find_place(text: str) -> str | None:
    """An issuing authority line — free text, so only obvious noise is rejected.

    ⚠️ Deliberately permissive: `IssuePlaceNormalizer` (Domain) is what turns
    whatever survives here into one of exactly two canonical values, or None.
    Being strict twice would only lose readings that the normalizer could have
    rescued.
    """
    candidate = _strip_label(text).strip()
    if len(candidate) < 8 or any(character.isdigit() for character in candidate):
        return None
    if is_printed_boilerplate(candidate):
        return None
    return " ".join(candidate.split())


FINDERS = {
    FieldKey.ID_NUMBER: find_id_number,
    FieldKey.FULL_NAME: find_name,
    FieldKey.DATE_OF_BIRTH: find_date,
    FieldKey.ISSUE_DATE: find_date,
    FieldKey.EXPIRY_DATE: find_expiry,
    FieldKey.ISSUE_PLACE: find_place,
}


def _strip_label(text: str) -> str:
    """Drop a `Họ và tên / Full name:` style prefix sharing the value's line."""
    stripped = _LABEL_TAIL.sub("", text, count=1)
    return stripped if stripped else text


def _digits_only_spacing(text: str) -> str:
    """Close the gaps a recognizer opens inside a long digit run.

    `001 087 043408` is one number that happens to be printed with spacing;
    without this it is three numbers, none of them twelve digits long.
    """
    return re.sub(r"(?<=\d) (?=\d)", "", text)


def looks_like_a_label(text: str, anchors: list[str], threshold: float) -> bool:
    """Whether this text is a printed label rather than a value."""
    return matches_any(text, anchors, threshold)
