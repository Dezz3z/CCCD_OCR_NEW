"""Pure TD1 (ICAO 9303 part 5) string handling — no images, no I/O (§7.4.4).

Split from `mrz_reader.py` so the checksum and repair logic can be tested
against fixed strings without an OCR engine anywhere in sight.

⭐ Vietnamese CCCD layout, verified against a real card:

```
IDVNM179002546204817900254 6<<2
7902273F3902275VNM<<<<<<<<<<<2
VO<<HUYNH<NGAN<GIAO<<<<<<<<<<
```

| Line | Position | Content |
|---|---|---|
| 1 | 0–4 | `ID` + `VNM` |
| 1 | 5–13 | ⭐ the **old 9-digit CMND**, not the CCCD |
| 1 | 14 | check digit over 5–13 |
| 1 | 15–26 | ⭐ the **12-digit CCCD**, carried in optional data |
| 1 | 27–28 | `<` filler |
| 1 | 29 | check digit over 15–28 |
| 2 | 0–5 | date of birth `YYMMDD` |
| 2 | 6 | check digit over 0–5 |
| 2 | 7 | sex `M`/`F`/`<` |
| 2 | 8–13 | ⭐ **date of expiry** — the field no other channel provides |
| 2 | 14 | check digit over 8–13 |
| 2 | 15–17 | nationality |
| 2 | 29 | composite check digit |
| 3 | 0–29 | surname `<<` given names, unaccented |
"""
from __future__ import annotations

from dataclasses import dataclass

LINE_LENGTH = 30
LINE_COUNT = 3
FILLER = "<"

_WEIGHTS = (7, 3, 1)

# Characters outside [A-Z0-9<] that still have an obvious intended glyph.
_SYMBOL_LOOKALIKES = {
    "|": "1",
    "!": "1",
    "«": FILLER,
    "‹": FILLER,  # noqa: RUF001 — an angle quote is a common `<` misread
    "(": FILLER,
    "[": FILLER,
}

# ⭐ Letter→digit forcing is applied ONLY to spans TD1 defines as numeric.
# A global map would corrupt names: `D`, `O`, `S`, `B` are all legitimate in
# `HOANG`, `DUNG`, `SON`. This is what "charset_hint is a post-processing
# filter, not a decode constraint" means in practice (CLAUDE.md pitfall #3).
_LETTER_TO_DIGIT = {
    "O": "0", "Q": "0", "D": "0",
    "I": "1", "L": "1",
    "Z": "2",
    "S": "5",
    "G": "6",
    "T": "7",
    "B": "8",
    "A": "4",
}

# Digits OCR most often swaps for one another; drives the bounded repair.
_DIGIT_ALTERNATIVES = {
    "0": ("8", "6", "9"),
    "1": ("7", "4"),
    "2": ("7", "3"),
    "3": ("8", "9", "5"),
    "4": ("1", "9"),
    "5": ("6", "8", "3"),
    "6": ("5", "8", "0"),
    "7": ("1", "2"),
    "8": ("0", "6", "3"),
    "9": ("4", "3", "0"),
}

MAX_REPAIR_EDITS = 3

# (start, end_exclusive, check_digit_position) for every checksummed numeric span.
_LINE1_GROUPS = ((5, 14, 14), (15, 29, 29))
_LINE2_GROUPS = ((0, 6, 6), (8, 14, 14))


@dataclass(frozen=True, slots=True)
class Td1Fields:
    """The values TD1 carries, before any business normalization."""

    document_number: str
    citizen_id: str
    date_of_birth: str
    date_of_expiry: str
    sex: str
    surname: str
    given_names: str


@dataclass(frozen=True, slots=True)
class Td1Parse:
    """Outcome of reading a TD1 block: values plus how much we trust them."""

    fields: Td1Fields
    lines: list[str]
    checksum_valid: bool
    corrections_applied: int


def force_charset(text: str) -> str:
    """Map characters into `[A-Z0-9<]` without touching letters that belong there.

    Anything with no plausible lookalike becomes filler rather than being
    dropped, so downstream position arithmetic stays aligned.
    """
    forced: list[str] = []
    for char in text:
        upper = char.upper()
        if (upper.isascii() and (upper.isdigit() or ("A" <= upper <= "Z"))) or upper == FILLER:
            forced.append(upper)
        else:
            forced.append(_SYMBOL_LOOKALIKES.get(char, FILLER))
    return "".join(forced)


def digitize(value: str) -> str:
    """Force a span TD1 defines as numeric into digits by glyph similarity."""
    return "".join(_LETTER_TO_DIGIT.get(char, char) for char in value)


def normalize_lines(raw: str) -> list[str]:
    """Coerce recognized text into exactly 3 lines of 30 characters.

    Whitespace is dropped rather than treated as filler: OCR inserts spaces
    between glyph clusters, and treating them as `<` would shift every field.
    """
    candidates = [
        force_charset("".join(line.split()))
        for line in raw.splitlines()
        if line.strip()
    ]

    if len(candidates) != LINE_COUNT:
        joined = "".join(candidates)
        candidates = [
            joined[index : index + LINE_LENGTH]
            for index in range(0, LINE_COUNT * LINE_LENGTH, LINE_LENGTH)
        ]

    return [line.ljust(LINE_LENGTH, FILLER)[:LINE_LENGTH] for line in candidates]


def check_digit(value: str) -> str:
    """ICAO 9303 7-3-1 weighted modulus-10 check digit."""
    total = 0
    for index, char in enumerate(value):
        if char.isdigit():
            weight_value = int(char)
        elif "A" <= char <= "Z":
            weight_value = ord(char) - ord("A") + 10
        else:
            weight_value = 0
        total += weight_value * _WEIGHTS[index % len(_WEIGHTS)]
    return str(total % 10)


def parse(lines: list[str]) -> Td1Parse:
    """Parse a normalized 3x30 block, repairing check-digit failures if it can."""
    line1 = _digitize_spans(lines[0], _LINE1_GROUPS)
    line2 = _digitize_spans(lines[1], _LINE2_GROUPS)
    line3 = lines[2]

    line1, edits1 = _repair(line1, _LINE1_GROUPS)
    line2, edits2 = _repair(line2, _LINE2_GROUPS)
    repaired = [line1, line2, line3]

    surname, _, given = line3.partition(FILLER * 2)
    fields = Td1Fields(
        document_number=line1[5:14].strip(FILLER),
        citizen_id=line1[15:27].strip(FILLER),
        date_of_birth=line2[0:6],
        date_of_expiry=line2[8:14],
        sex=line2[7],
        surname=surname.replace(FILLER, " ").strip(),
        given_names=given.replace(FILLER, " ").strip(),
    )
    return Td1Parse(
        fields=fields,
        lines=repaired,
        checksum_valid=_all_checks_pass(repaired),
        corrections_applied=edits1 + edits2,
    )


def _digitize_spans(line: str, groups: tuple[tuple[int, int, int], ...]) -> str:
    chars = list(line)
    for start, end, digit_position in groups:
        for index in range(start, end):
            chars[index] = _LETTER_TO_DIGIT.get(chars[index], chars[index])
        chars[digit_position] = _LETTER_TO_DIGIT.get(
            chars[digit_position], chars[digit_position]
        )
    return "".join(chars)


def _all_checks_pass(lines: list[str]) -> bool:
    line1, line2, _ = lines
    groups = (
        (line1[5:14], line1[14]),
        (line1[15:29], line1[29]),
        (line2[0:6], line2[6]),
        (line2[8:14], line2[14]),
    )
    if not all(check_digit(value) == expected for value, expected in groups):
        return False
    composite = line1[5:30] + line2[0:7] + line2[8:15] + line2[18:29]
    return check_digit(composite) == line2[29]


def _repair(line: str, groups: tuple[tuple[int, int, int], ...]) -> tuple[str, int]:
    """Fix check-digit failures by trying visually-similar digits.

    ⭐ Bounded at `MAX_REPAIR_EDITS` substitutions per group: an unbounded
    search would eventually satisfy any check digit and manufacture confident
    garbage — worse than admitting the read failed.
    """
    chars = list(line)
    edits = 0
    for start, end, digit_position in groups:
        value = "".join(chars[start:end])
        if check_digit(value) == chars[digit_position]:
            continue
        fixed = _search(value, chars[digit_position])
        if fixed is None:
            continue
        for offset, char in enumerate(fixed):
            if chars[start + offset] != char:
                edits += 1
            chars[start + offset] = char
    return "".join(chars), edits


def _search(value: str, expected: str) -> str | None:
    positions = [index for index, char in enumerate(value) if char in _DIGIT_ALTERNATIVES]
    return _search_from(list(value), positions, expected, 0, MAX_REPAIR_EDITS)


def _search_from(
    chars: list[str],
    positions: list[int],
    expected: str,
    start: int,
    budget: int,
) -> str | None:
    if check_digit("".join(chars)) == expected:
        return "".join(chars)
    if budget == 0:
        return None
    for cursor in range(start, len(positions)):
        index = positions[cursor]
        original = chars[index]
        for alternative in _DIGIT_ALTERNATIVES[original]:
            chars[index] = alternative
            found = _search_from(chars, positions, expected, cursor + 1, budget - 1)
            if found is not None:
                return found
        chars[index] = original
    return None
