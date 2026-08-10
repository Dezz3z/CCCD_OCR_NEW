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

# ⭐ The same date with every separator dropped — `04062025`. Measured on a real
# Căn cước 2024 back, where the recognizer swallowed both slashes and the issue
# date went unread entirely. Only tried after `_DATE` fails, and only on a run
# that is exactly 8 digits long, so it cannot bite a chunk out of the 12-digit
# citizen id or an MRZ line.
_DATE_NO_SEPARATOR = re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{4})(?!\d)")

# Bounds on a plausible printed year. Loose enough for any real card, tight
# enough that an 8-digit run which is not a date usually fails here.
_MIN_YEAR, _MAX_YEAR = 1900, 2100

# The CCCD number: exactly 12 digits, not part of a longer run.
_ID_NUMBER = re.compile(r"(?<!\d)(\d{12})(?!\d)")

# Cards issued without an expiry print this instead of a date.
NO_EXPIRY = "KHÔNG THỜI HẠN"

# ⚠️ **This guard cannot fire on the current recognizer, and that is deliberate
# after measuring.** Swept over all 774 recognized lines in the sample:
#
# | Line | Score |
# |---|---|
# | `PHAM THI PHU'O'NG THOA` — a person's name | **76.2** ← highest of all |
# | `Tan Minh,Thuo'ng Tin,Ha Noi` — an address | 75.0 |
# | `ovong thoi hg` — ⭐ the **genuine** value on a Căn cước 2024 back | **69.8** |
#
# The true value scores *below* the noise, so no threshold accepts it without
# first accepting a name. Token-wise matching does not rescue it either: of
# `KHÔNG THỜI HẠN` only `THỜI` survived recognition at all.
#
# Leaving the field unread is the correct outcome — `expiry_date` is optional
# and a blank the user fills in beats a confident wrong value. The constant
# stays for a future recognizer that reads the phrase legibly.
#
# ⚠️ An earlier comment here claimed this string scored 80 and was noise "from
# an unrelated part of a real card". Both halves were wrong: it scores 69.8,
# and it is the expiry field of a card generation the design did not yet know
# existed.
_NO_EXPIRY_THRESHOLD = 85.0


# A name line is letters and spaces only — no digits, no punctuation beyond the
# apostrophe the recognizer emits for the horn diacritic.
_NAME_LINE = re.compile(r"^[A-Za-zÀ-ỹ' ]{4,}$")

# Labels sit on the same line as their value often enough that the label text
# has to be stripped before the value can be read.
_LABEL_TAIL = re.compile(r"^.*?[:;]\s*")

# Two or more digits together. A printed number always has one; a letter the
# recognizer mistook for a digit (`CÔNG` → `C0NG`) never does.
_DIGIT_RUN = re.compile(r"\d{2}")

MIN_NAME_WORDS = 2
MIN_PLACE_LENGTH = 8


def find_id_number(text: str) -> str | None:
    """The 12-digit citizen id, if this text carries one."""
    match = _ID_NUMBER.search(_digits_only_spacing(text))
    return match.group(1) if match else None


def find_date(text: str) -> str | None:
    """A `dd/mm/yyyy` date, normalized to that exact shape.

    ⭐ Returned with slashes regardless of what the recognizer produced, so the
    validation layer sees one format and fusion compares like with like.

    Separated dates are tried first; a bare 8-digit run is only read as a date
    when nothing better is present, because that shape is far weaker evidence.
    """
    for pattern in (_DATE, _DATE_NO_SEPARATOR):
        match = pattern.search(text)
        if match is None:
            continue
        day, month, year = match.groups()
        if _is_a_plausible_date(day, month, year):
            return f"{day}/{month}/{year}"
    return None


def _is_a_plausible_date(day: str, month: str, year: str) -> bool:
    """Calendar-shaped, without pretending to know how long each month is."""
    return (
        1 <= int(day) <= 31
        and 1 <= int(month) <= 12
        and _MIN_YEAR <= int(year) <= _MAX_YEAR
    )


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

    ⭐ Rejecting on *any* digit was strict twice, and it cost a real reading:
    the recognizer renders `BỘ CÔNG AN` as `BO C0NG AI`, and that lone `0` threw
    away the whole line. What the rule is actually for is telling this field
    apart from the date and id printed near it, so it now looks for a **run** of
    digits — which a number always has and a misread letter never does.
    """
    candidate = _strip_label(text).strip()
    if len(candidate) < MIN_PLACE_LENGTH or _DIGIT_RUN.search(candidate):
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
