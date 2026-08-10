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

# Where each line's trailing "filler run then one check digit" begins.
_LINE1_TAIL_START = 27
_LINE2_TAIL_START = 18

# --- line selection -----------------------------------------------------------
# A recognized line must be at least this long to be considered part of the MRZ.
MIN_LINE_LENGTH = 18
_TD1_ALPHABET = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<")
_LINE1_LEAD = frozenset("I1")
_LINE1_DIGIT_RATIO = 0.70
_LINE2_DIGIT_RATIO = 0.80
_LINE3_MAX_DIGIT_RATIO = 0.35


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
    """Outcome of reading a TD1 block: values plus how much we trust them.

    ⭐ `checksum_valid` reflects the FOUR per-field check digits, not the
    composite. See `group_checks_pass` for why they were separated.
    """

    fields: Td1Fields
    lines: list[str]
    checksum_valid: bool
    composite_valid: bool
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


def alphabet_density(line: str) -> float:
    """Fraction of characters already inside the TD1 alphabet, before any mapping.

    Measured on the RAW recognized text on purpose: the printed address block
    that sits directly above the MRZ is mixed-case and accented, so it scores
    low here and high after `force_charset` — which is exactly the distinction
    that keeps it out of the MRZ.
    """
    if not line:
        return 0.0
    return sum(character in _TD1_ALPHABET for character in line) / len(line)


def classify_line(line: str) -> int | None:
    """Which TD1 line this is (0, 1 or 2), by structure alone — or None.

    ⭐ Position in the image is NOT used. Recognition regularly misses one of
    the three lines, and assuming "first line found is line 1" is what turns a
    missed line into six confidently-wrong fields: the name line lands in
    line 1's slot and its letters get force-digitized into a citizen id.
    """
    normalized = force_charset(line)
    if len(normalized) < MIN_LINE_LENGTH:
        return None

    # Line 1: `ID` + issuing state, then a long run of digits (both id numbers).
    if normalized[0] in _LINE1_LEAD and _digit_ratio(normalized[5:29]) >= _LINE1_DIGIT_RATIO:
        return 0

    # Line 2: YYMMDD + check + sex + YYMMDD + check + nationality. ⭐ The sex
    # position is tested for "not a digit" rather than for `M`/`F`/`<`: a real
    # card came back with `E` there, and rejecting the line over one misread
    # glyph throws away the two date fields sitting either side of it.
    if (
        len(normalized) > 14
        and _digit_ratio(normalized[0:6]) >= _LINE2_DIGIT_RATIO
        and not normalized[7].isdigit()
        and _digit_ratio(normalized[8:14]) >= _LINE2_DIGIT_RATIO
    ):
        return 1

    # Line 3: names, so essentially no digits.
    if _digit_ratio(normalized) <= _LINE3_MAX_DIGIT_RATIO:
        return 2
    return None


def select_lines(raw: str) -> list[str] | None:
    """Pick the TD1 block out of everything recognized in the band.

    Returns 3 lines of 30 characters, or None when lines 1 and 2 are not both
    present — those two carry every field MRZ contributes, so without them
    there is nothing to report and guessing would be worse than silence.
    """
    candidates: list[str] = []
    for line in raw.splitlines():
        collapsed = "".join(line.split())
        if len(collapsed) < MIN_LINE_LENGTH or alphabet_density(collapsed) < 0.80:
            continue
        # Recognition sometimes returns the whole block as one run of text.
        if len(collapsed) >= 2 * LINE_LENGTH:
            candidates.extend(
                collapsed[index : index + LINE_LENGTH]
                for index in range(0, len(collapsed), LINE_LENGTH)
            )
        else:
            candidates.append(collapsed)

    slots: list[str | None] = [None, None, None]
    for candidate in candidates:
        slot = classify_line(candidate)
        if slot is not None and slots[slot] is None:
            slots[slot] = force_charset(candidate)

    if slots[0] is None or slots[1] is None:
        return None
    return [
        (line or "").ljust(LINE_LENGTH, FILLER)[:LINE_LENGTH] for line in slots
    ]


def _digit_ratio(value: str) -> float:
    if not value:
        return 0.0
    return sum(character.isdigit() for character in value) / len(value)


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
    line1 = _realign_tail(lines[0], _LINE1_TAIL_START)
    line2 = _realign_tail(lines[1], _LINE2_TAIL_START)
    line1 = _digitize_spans(line1, _LINE1_GROUPS)
    line2 = _digitize_spans(line2, _LINE2_GROUPS)
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
    corrections = edits1 + edits2
    composite_valid = composite_check_passes(repaired)
    return Td1Parse(
        fields=fields,
        lines=repaired,
        checksum_valid=_is_trustworthy(repaired, corrections, composite_valid),
        composite_valid=composite_valid,
        corrections_applied=corrections,
        )


def _is_trustworthy(lines: list[str], corrections: int, composite_valid: bool) -> bool:
    """⭐ A repaired block must be corroborated; a clean one speaks for itself.

    The four group checks alone are not a safe gate once `_repair` is allowed
    to substitute digits: given three edits per group it can satisfy almost any
    check digit, which is how a block of pure noise ends up "valid". The
    composite digit is the independent witness — it covers the same characters
    under different weights, so a repair that satisfies one rarely satisfies
    the other by accident.

    So repairs are trusted only when the composite agrees. Clean reads do not
    need it, which matters because the composite sits at the end of the filler
    run and is the column recognizers most often lose (see `_realign_tail`).

    ⚠️ **The composite does not witness line 1's document-number group.** Both
    sums start at `line1[5]` on the same 7-3-1 phase, and that group is exactly
    9 characters — three whole cycles — so every later column keeps its
    alignment. Any repair satisfying that group's check digit therefore leaves
    the composite unchanged too. It holds for the other three groups, whose
    phases differ by one position, and those are the only groups feeding a
    field to fusion (`_to_fields` never exports the document number).
    """
    if not group_checks_pass(lines):
        return False
    return composite_valid or corrections == 0


def _realign_tail(line: str, tail_start: int) -> str:
    """⭐ Put a check digit swallowed by the trailing `<` run back where it belongs.

    A TD1 line ends with a long filler run and then one check digit — eleven
    `<` in a row on line 2. Recognizers miscount identical glyph runs, so that
    digit arrives one to three columns early, or the run swallows it whole. It
    was the single largest cause of checksum failure on real cards: the data
    was right and only the last column was misplaced.

    Only an unambiguous case is touched — exactly one digit in the tail, and
    it is not already in the right place. Anything else is left alone.
    """
    tail = line[tail_start:LINE_LENGTH]
    digits = [character for character in tail if character.isdigit()]
    if len(digits) != 1 or tail[-1].isdigit():
        return line
    return line[:tail_start] + FILLER * (len(tail) - 1) + digits[0]


def _digitize_spans(line: str, groups: tuple[tuple[int, int, int], ...]) -> str:
    chars = list(line)
    for start, end, digit_position in groups:
        for index in range(start, end):
            chars[index] = _LETTER_TO_DIGIT.get(chars[index], chars[index])
        chars[digit_position] = _LETTER_TO_DIGIT.get(
            chars[digit_position], chars[digit_position]
        )
    return "".join(chars)


def group_checks_pass(lines: list[str]) -> bool:
    """The four per-field check digits — ⭐ the gate for trusting MRZ values.

    Split from the composite check on measured evidence. Every field the MRZ
    contributes (document number, citizen id, date of birth, date of expiry)
    is covered by one of these four, so passing all four means each value was
    independently verified. The composite adds redundancy over the *same*
    characters while sitting at the end of an eleven-character filler run —
    the one column recognizers reliably get wrong. Gating on it rejected
    correct data: it alone accounted for most checksum failures on real cards.
    """
    line1, line2, _ = lines
    groups = (
        (line1[5:14], line1[14]),
        (line1[15:29], line1[29]),
        (line2[0:6], line2[6]),
        (line2[8:14], line2[14]),
    )
    return all(check_digit(value) == expected for value, expected in groups)


def composite_check_passes(lines: list[str]) -> bool:
    """The whole-block check digit — a confidence bonus, not a gate."""
    line1, line2, _ = lines
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
