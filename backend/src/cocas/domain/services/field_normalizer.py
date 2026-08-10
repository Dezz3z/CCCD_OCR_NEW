"""FieldNormalizer — S9, the stage that makes three channels comparable (§03 S9, §7.2 D1).

⭐ **This service exists because of fusion, not because of storage.** QR emits
`13031987`, MRZ emits `13031987`, the OCR extractor emits `13/03/1987` — three
spellings of one date. Hand those to `FieldFusionService` unchanged and rule 3
(consensus bonus) never fires, while rule 4 (conflict detection) fires on
*every* card: two high-confidence sources "disagreeing" about a value they in
fact agree on. Normalization is what turns agreement into something a string
comparison can see.

So every field gets exactly one canonical spelling:

| Field | Canonical form | Why this one |
|---|---|---|
| `id_number` | 12 digits, no separators | the only form all three channels can produce |
| `full_name` | NFC, UPPERCASE, single-spaced | ⭐ NFC **before** uppercase (CLAUDE.md pitfall #2) |
| dates | ⭐ ISO `YYYY-MM-DD` | sorts, compares, and parses without a locale |
| `expiry_date` | ISO date **or** `KHÔNG THỜI HẠN` | absence of an expiry is a value, not a blank |
| `issue_place` | one of exactly 2 strings, or `None` | delegated to `IssuePlaceNormalizer` |

⚠️ `None` means "this channel could not produce a usable value here", never
"the field is empty on the card". A value that fails to normalize is dropped
rather than passed through raw: fusion has no way to tell a raw value from a
canonical one, so a single un-normalized survivor would be scored as a genuine
disagreement against the channels that did normalize.

**Never raises.** Every value object it uses can reject its input, and a
rejection here is an ordinary outcome (P-08) — the field comes back `None` with
a flag, and the user fills it in.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from rapidfuzz import fuzz

from cocas.domain.enums.field_key import FieldKey
from cocas.domain.exceptions import ValidationError
from cocas.domain.services.issue_place_normalizer import IssuePlaceNormalizer
from cocas.domain.value_objects._vn_text import (
    collapse_whitespace,
    is_vn_name_char,
    nfc_upper,
    strip_diacritics,
)
from cocas.domain.value_objects.citizen_id import CitizenId
from cocas.domain.value_objects.id_card_dates import NO_EXPIRY_TEXT
from cocas.domain.value_objects.person_name import PersonName, fix_ocr_digits

# Flags a normalized value can carry into fusion and validation. String
# constants rather than an enum because they travel to the UI inside JSONB
# alongside fusion's own flags, and one vocabulary beats two.
FLAG_DATE_REPAIRED = "DATE_REPAIRED"
FLAG_NO_EXPIRY = "NO_EXPIRY"
FLAG_ISSUE_PLACE_UNRECOGNIZED = "ISSUE_PLACE_UNRECOGNIZED"
FLAG_UNPARSEABLE = "UNPARSEABLE"

# ⭐ Ceiling for a date that only became valid after digit substitution. The
# value is a guess that happened to be the *only* self-consistent one — worth
# offering, never worth trusting past review (§03 S9).
REPAIRED_DATE_CONFIDENCE = 0.75

MIN_YEAR, MAX_YEAR = 1900, 2100

_DATE_SEPARATED = re.compile(r"^(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{4})$")
_DATE_COMPACT = re.compile(r"^(\d{2})(\d{2})(\d{4})$")

# ⭐ Digit pairs the recognizer confuses, applied ONLY to rescue a date that
# already failed to parse — see `_repair_date`.
_CONFUSABLE_DIGITS: dict[str, str] = {"1": "7", "7": "1", "3": "8", "8": "3", "0": "6", "6": "0"}

_NO_EXPIRY_STRIPPED = strip_diacritics(NO_EXPIRY_TEXT)
_NO_EXPIRY_THRESHOLD = 85.0

_DATE_FIELDS = frozenset({FieldKey.DATE_OF_BIRTH, FieldKey.ISSUE_DATE, FieldKey.EXPIRY_DATE})


@dataclass(frozen=True, slots=True)
class NormalizedValue:
    """One channel's value for one field, in canonical form.

    Mirrors `FusedField`'s invariant on purpose: `value is None` ⇒
    `confidence == 0.0`, so a dropped value can never carry weight into fusion.
    """

    value: str | None
    confidence: float
    flags: tuple[str, ...] = ()
    tier: int | None = None
    """`normalization_alias` tier that matched — `issue_place` only (§4.4.4)."""

    def __post_init__(self) -> None:
        if self.value is None and self.confidence != 0.0:
            raise ValueError("NormalizedValue with no value must have confidence 0.0")

    @property
    def is_no_expiry(self) -> bool:
        """⭐ True for a card that prints `KHÔNG THỜI HẠN` — a read value, not a blank."""
        return self.value == NO_EXPIRY_TEXT


_EMPTY = NormalizedValue(value=None, confidence=0.0, flags=(FLAG_UNPARSEABLE,))


class FieldNormalizer:
    """Domain Service — see module docstring for the canonical forms."""

    def __init__(self, issue_place_normalizer: IssuePlaceNormalizer) -> None:
        self._issue_place = issue_place_normalizer

    async def normalize(
        self, key: FieldKey, text: str | None, confidence: float
    ) -> NormalizedValue:
        """Canonicalize one channel's reading of one field. Never raises."""
        raw = collapse_whitespace(text or "")
        if not raw:
            return _EMPTY

        confidence = _clamp(confidence)
        if key is FieldKey.ID_NUMBER:
            return _wrap(_normalize_id_number(raw), confidence)
        if key is FieldKey.FULL_NAME:
            return _wrap(_normalize_name(raw), confidence)
        if key is FieldKey.EXPIRY_DATE:
            return _normalize_expiry(raw, confidence)
        if key in _DATE_FIELDS:
            return _normalize_date_field(raw, confidence)
        if key is FieldKey.ISSUE_PLACE:
            return await self._normalize_issue_place(raw, confidence)
        return _EMPTY  # unreachable while FieldKey has 6 members; keeps the match total

    async def normalize_channel(
        self, fields: Mapping[FieldKey, str], confidence: float
    ) -> dict[FieldKey, NormalizedValue]:
        """Normalize a whole channel's output, where one confidence covers every field.

        ⭐ QR and MRZ vouch for their read as a block — a valid checksum says the
        whole MRZ is right, not that the date of birth alone is. The OCR channel
        is the opposite (every field carries its own recognizer score) and calls
        `normalize()` per field instead.
        """
        result: dict[FieldKey, NormalizedValue] = {}
        for key, text in fields.items():
            result[key] = await self.normalize(key, text, confidence)
        return result

    async def _normalize_issue_place(self, raw: str, confidence: float) -> NormalizedValue:
        outcome = await self._issue_place.normalize(raw)
        if outcome.value is None:
            return NormalizedValue(
                value=None, confidence=0.0, flags=(FLAG_ISSUE_PLACE_UNRECOGNIZED,)
            )
        # ⭐ min(), not a product: the two numbers measure different things —
        # how clearly the line was read, and how sure the match was. A value is
        # no better than its weakest step, but multiplying two independent
        # "quite sure"s down to "unsure" would send clean tier-1 matches to
        # manual review for no reason.
        return NormalizedValue(
            value=outcome.value,
            confidence=min(confidence, outcome.confidence),
            tier=outcome.tier or None,
        )


def _normalize_id_number(raw: str) -> str | None:
    """12 digits, with the letter-for-digit misreads the VO already knows about."""
    try:
        return CitizenId.from_ocr_text(raw).value
    except ValidationError:
        return None


def _normalize_name(raw: str) -> str | None:
    """NFC → UPPERCASE → collapse → fix digits between letters → drop the rest.

    ⚠️ **That order is load-bearing**, and §03 S9 spells it out: repair before
    filtering. Filter first and `H0ANG` has its `0` deleted as out-of-charset,
    leaving `HANG` — a plausible-looking name that is not the one on the card.

    ⚠️ Drops disallowed characters instead of rejecting the whole name. A name
    arrives from OCR with its diacritics already lost (§7.4.5) and sometimes
    with a stray glyph; keeping `NGUYEN VAN AN` beats dropping the field
    because one comma survived recognition.
    """
    repaired = fix_ocr_digits(collapse_whitespace(nfc_upper(raw)))
    cleaned = collapse_whitespace("".join(ch for ch in repaired if is_vn_name_char(ch)))
    if not cleaned:
        return None
    try:
        return PersonName(cleaned).value
    except ValidationError:
        return None


def _normalize_expiry(raw: str, confidence: float) -> NormalizedValue:
    """A date, or the words a lifelong card prints instead.

    ⚠️ The fuzzy tier is kept for a future recognizer, not for this one: the
    genuine phrase scores 69.8 on the current model while a person's name scores
    76.2 (§7.4.6), so no threshold accepts the real value without accepting
    names first. Exact match after folding diacritics is what actually fires —
    the extractor hands over the canonical constant when it recognizes the line.
    """
    folded = strip_diacritics(nfc_upper(raw))
    if folded == _NO_EXPIRY_STRIPPED or fuzz.ratio(folded, _NO_EXPIRY_STRIPPED) >= _NO_EXPIRY_THRESHOLD:
        return NormalizedValue(
            value=NO_EXPIRY_TEXT, confidence=confidence, flags=(FLAG_NO_EXPIRY,)
        )
    return _normalize_date_field(raw, confidence)


def _normalize_date_field(raw: str, confidence: float) -> NormalizedValue:
    parsed = _parse_date(raw)
    if parsed is not None:
        return NormalizedValue(value=parsed.isoformat(), confidence=confidence)

    repaired = _repair_date(raw)
    if repaired is not None:
        return NormalizedValue(
            value=repaired.isoformat(),
            confidence=min(confidence, REPAIRED_DATE_CONFIDENCE),
            flags=(FLAG_DATE_REPAIRED,),
        )
    return _EMPTY


def _parse_date(raw: str) -> date | None:
    """`dd/mm/yyyy`, `dd-mm-yyyy`, `dd.mm.yyyy` or `ddmmyyyy` → a real calendar date."""
    digits = _date_digits(raw)
    if digits is None:
        return None
    day, month, year = int(digits[0:2]), int(digits[2:4]), int(digits[4:8])
    if not MIN_YEAR <= year <= MAX_YEAR:
        return None
    try:
        return date(year, month, day)
    except ValueError:  # 31/02, month 13, day 0 — all land here
        return None


def _date_digits(raw: str) -> str | None:
    """The 8 digits of a date, whatever separators were printed between them."""
    compact = _DATE_COMPACT.match(raw.replace(" ", ""))
    if compact is not None:
        return "".join(compact.groups())
    separated = _DATE_SEPARATED.match(raw)
    if separated is None:
        return None
    day, month, year = separated.groups()
    return f"{day.zfill(2)}{month.zfill(2)}{year}"


def _repair_date(raw: str) -> date | None:
    """Substitute ONE confusable digit in the day or month, if that makes it a date.

    ⭐ Only reached when the text failed to parse as-is — and that ordering is
    the whole safety argument. Run substitutions on a date that already parsed
    and `01/01/1990` yields `07/01/1990` and `01/07/1990` too, all valid, all
    equally plausible; the "unique valid date" rule would then reject the
    reading the card actually printed.

    ⚠️ **Two guards beyond what §03 S9 specifies, both added after the wider
    search was seen inventing values:**

    * **The year is never substituted.** Searching all 8 digits turns
      `29/02/2023` — a date that does not exist and that §8.11 lists as a
      mandatory *invalid* case — into `2028-02-29`, the one self-consistent
      reading in the whole space. A repair that moves someone's birth year by
      five years to make the calendar work is not a repair.
    * **At most one digit changes.** One garbled glyph is the recognizer's
      normal failure; two in the same eight-digit field is rare, and allowing
      it makes `00/00/1990` "uniquely" `06/06/1990`. Bounding the search to a
      single substitution is what makes "unique valid reading" mean something —
      there are at most 4 candidates, not 256.

    Neither guard costs a repair anyone has measured: the sample's dates read
    12/12 and 2/2 without this pass ever firing (§7.4.7).
    """
    digits = _date_digits(raw)
    if digits is None:
        return None

    found: set[date] = set()
    for variant in _single_substitutions(digits):
        day, month, year = int(variant[0:2]), int(variant[2:4]), int(variant[4:8])
        if not MIN_YEAR <= year <= MAX_YEAR:
            continue
        try:
            found.add(date(year, month, day))
        except ValueError:
            continue
        if len(found) > 1:
            return None  # ambiguous — two readings are equally defensible
    return found.pop() if len(found) == 1 else None


def _single_substitutions(digits: str) -> list[str]:
    """The ≤4 readings reachable by swapping one confusable digit of the day or month."""
    variants = []
    for index in range(4):  # ddmm only — positions 4..7 are the year
        alternative = _CONFUSABLE_DIGITS.get(digits[index])
        if alternative is not None:
            variants.append(digits[:index] + alternative + digits[index + 1 :])
    return variants


def _wrap(value: str | None, confidence: float) -> NormalizedValue:
    if value is None:
        return _EMPTY
    return NormalizedValue(value=value, confidence=confidence)


def _clamp(confidence: float) -> float:
    return min(max(confidence, 0.0), 1.0)
