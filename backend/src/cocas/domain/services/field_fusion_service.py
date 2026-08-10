"""FieldFusionService — the 8 merge rules of S10 (§7.5.2, §12.6, §03 S10).

⭐ P-04 lives here: extraction is never "just OCR" — every field's final value
is the outcome of fusing up to three independent channels.

| # | Rule | Where |
|---|---|---|
| 1 | Collect 0–3 candidates per field | `fuse()` |
| 2 | Source priority · OCR scaled by a per-field factor | `_base_score` |
| 3 | Consensus bonus `+0.10`, capped at 1.00 | `_fuse_field` |
| 4 | Two sources ≥ 0.90 disagreeing → keep the higher-priority value at **0.50** | `_detect_conflict` |
| 5 | ⭐ QR id ≠ MRZ id → `CARD_MISMATCH` | `_flag_card_mismatch` |
| 6 | ⭐ Structure of the id number vs the birth date it should encode | `_check_id_consistency` |
| 7 | Weighted overall score | `ConfidenceCalculator` |
| 8 | `needs_review` below the threshold | `_fuse_field` |

**Invariants** (§12.6): the result always has all 6 keys · `confidence ∈ [0, 1]`
absolutely · `value is None ⇒ confidence == 0 and source == NONE`.

**Not this service's job:** deciding whether anything is blocking — that is
`ValidationEngine`, which reads the flags raised here (V-OCR-019/020) — and
changing a value. Fusion picks between readings; it never edits one.

⚠️ Candidates must arrive **already normalized** (`FieldNormalizer`, S9). Rule 3
compares values with `==`, so `13/03/1987` and `13031987` are two different
answers to this service, and rule 4 would then report a conflict on a card where
all three channels actually agree.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from cocas.domain.enums.field_key import FieldKey
from cocas.domain.enums.field_source import FieldSource
from cocas.domain.exceptions import ValidationError
from cocas.domain.value_objects.citizen_id import CitizenId

FLAG_SOURCE_CONFLICT = "SOURCE_CONFLICT"
FLAG_CARD_MISMATCH = "CARD_MISMATCH"
FLAG_ID_INCONSISTENT = "ID_INCONSISTENT"

CONSENSUS_BONUS = 0.10
MAX_CONFIDENCE = 1.0
DEFAULT_REVIEW_THRESHOLD = 0.85

# Rule 4: how confident two sources both have to be before their disagreement
# is treated as a real conflict rather than one of them simply being unsure.
CONFLICT_MIN_CONFIDENCE = 0.90

# ⭐ What a field is worth once two pieces of evidence contradict each other.
# Deliberately below `DEFAULT_REVIEW_THRESHOLD`: the value on offer is the
# better-sourced of two readings that cannot both be right, and a human has to
# look. Used by rules 4 and 6 alike — the epistemic situation is the same.
CONTRADICTED_CONFIDENCE = 0.50

_SOURCE_PRIORITY: dict[FieldSource, int] = {
    FieldSource.QR: 0,
    FieldSource.MRZ: 1,
    FieldSource.OCR: 2,
    FieldSource.MANUAL: 3,
    FieldSource.NONE: 4,
}

# ⭐ Rule 2's "OCR nhân hệ số trường". The factor says how much a *recognizer*
# reading of this particular field is worth, which is not the same question as
# how clearly the pixels were read — that is already in `candidate.confidence`.
#
# Seeded from what week 3 measured on the user's real photos (§7.4.6, §7.4.7),
# not chosen by feel. ⚠️ Small samples; the Golden Set is what turns these into
# calibrated numbers, and `FusionContext.ocr_field_factors` exists so they can
# be overridden from `system_setting` without a release.
OCR_FIELD_FACTORS: Mapping[FieldKey, float] = {
    # 14/14. A 12-digit run is self-checking: a misread digit usually breaks
    # the length, and `FieldNormalizer` drops anything that is not exactly 12.
    FieldKey.ID_NUMBER: 1.00,
    # ⭐ 11/15 exact — and the misses are systematic, not random. The `latin`
    # recognition model has no output for 38 of the 42 accented Vietnamese
    # capitals (§7.4.5), so an OCR-only name is usually *right but unaccented*.
    # That is precisely a value worth offering and not worth trusting.
    FieldKey.FULL_NAME: 0.75,
    # 12/12 and 2/2. The normalizer only accepts a real calendar date, which
    # rejects most misreads outright; the separator-less path is weaker.
    FieldKey.DATE_OF_BIRTH: 0.95,
    FieldKey.ISSUE_DATE: 0.95,
    FieldKey.EXPIRY_DATE: 0.95,
    # 1.00 on purpose, **not** a missing entry: `IssuePlaceNormalizer` has
    # already capped this value by its own match tier (S9), so a second factor
    # here would charge the same uncertainty twice.
    FieldKey.ISSUE_PLACE: 1.00,
}


@dataclass(frozen=True, slots=True)
class Candidate:
    """One channel's already-normalized value for a field.

    `confidence` is the channel's own — QR 1.00, MRZ 0.98 with a valid
    checksum / 0.90 repaired / 0.50 without, OCR the recognizer's score
    (§7.4.3, §7.4.4). Rule 2's per-field factor is applied here, not there.
    """

    value: str | None
    source: FieldSource
    confidence: float


@dataclass(frozen=True, slots=True)
class FusionContext:
    """Tuning passed into `fuse()` — kept minimal on purpose (P-10)."""

    review_threshold: float = DEFAULT_REVIEW_THRESHOLD
    ocr_field_factors: Mapping[FieldKey, float] = field(default_factory=lambda: OCR_FIELD_FACTORS)
    known_province_codes: frozenset[str] = frozenset()
    """The 63 codes from `province_code`. Empty ⇒ rule 6 skips the province check."""


@dataclass(frozen=True, slots=True)
class FusedField:
    """The winning value for one field, plus how confident and how it was chosen."""

    value: str | None
    confidence: float
    source: FieldSource
    needs_review: bool
    flags: tuple[str, ...] = ()
    agreement: bool = False
    """Rule 3 — two or more sources independently produced this same value."""

    def with_flag(self, flag: str, *, confidence: float | None = None) -> FusedField:
        """A copy carrying one more flag, and optionally a lowered confidence."""
        lowered = self.confidence if confidence is None else min(self.confidence, confidence)
        return FusedField(
            value=self.value,
            confidence=lowered,
            source=self.source,
            needs_review=self.needs_review or lowered < DEFAULT_REVIEW_THRESHOLD,
            flags=(*self.flags, flag),
            agreement=self.agreement,
        )


_NOTHING = FusedField(
    value=None, confidence=0.0, source=FieldSource.NONE, needs_review=True
)


class FieldFusionService:
    """Domain Service — see module docstring for the 8 rules and their invariants."""

    def fuse(
        self, candidates: Mapping[FieldKey, list[Candidate]], context: FusionContext
    ) -> dict[FieldKey, FusedField]:
        result: dict[FieldKey, FusedField] = {}
        for key in FieldKey:  # rule 1 — all 6 keys, present or not
            result[key] = self._fuse_field(key, list(candidates.get(key, [])), context)
        self._flag_card_mismatch(candidates, result)
        self._check_id_consistency(result, context)
        return result

    def _fuse_field(
        self, key: FieldKey, field_candidates: list[Candidate], context: FusionContext
    ) -> FusedField:
        usable = [c for c in field_candidates if c.value]
        if not usable:
            return _NOTHING

        # One best candidate per source (highest score wins a source's slot).
        best_per_source: dict[FieldSource, tuple[float, Candidate]] = {}
        for candidate in usable:
            score = self._base_score(key, candidate, context)  # rule 2
            current = best_per_source.get(candidate.source)
            if current is None or score > current[0]:
                best_per_source[candidate.source] = (score, candidate)

        # Rule 3 — how many distinct sources back each value.
        votes: dict[str, int] = {}
        for _, candidate in best_per_source.values():
            assert candidate.value is not None
            votes[candidate.value] = votes.get(candidate.value, 0) + 1

        scored: list[tuple[float, int, Candidate]] = []
        for score, candidate in best_per_source.values():
            assert candidate.value is not None
            bonus = CONSENSUS_BONUS * (votes[candidate.value] - 1)
            scored.append(
                (min(score + bonus, MAX_CONFIDENCE), _SOURCE_PRIORITY[candidate.source], candidate)
            )

        # Highest score wins; ties broken by source priority (lower = better).
        scored.sort(key=lambda item: (-item[0], item[1]))
        winning_score, _, winner = scored[0]
        assert winner.value is not None

        fused = FusedField(
            value=winner.value,
            confidence=winning_score,
            source=winner.source,
            needs_review=winning_score < context.review_threshold,  # rule 8
            agreement=votes[winner.value] > 1,
        )
        return self._detect_conflict(fused, best_per_source)  # rule 4

    def _base_score(self, key: FieldKey, candidate: Candidate, context: FusionContext) -> float:
        """Rule 2 — the channel's confidence, scaled for OCR by the field's factor."""
        score = min(max(candidate.confidence, 0.0), MAX_CONFIDENCE)
        if candidate.source is FieldSource.OCR:
            score *= context.ocr_field_factors.get(key, 1.0)
        return score

    def _detect_conflict(
        self, fused: FusedField, best_per_source: dict[FieldSource, tuple[float, Candidate]]
    ) -> FusedField:
        """⭐ Rule 4 — two sources that are both sure, and disagree.

        Only a disagreement *between confident sources* is a conflict. Two weak
        readings differing is ordinary noise, and the winner's own low score
        already sends it to review; raising a flag there would train users to
        ignore the flag.

        The higher-priority source keeps the field — but at
        `CONTRADICTED_CONFIDENCE`, because the honest statement is "one of these
        two is wrong and we do not know which", not "QR said so".
        """
        confident = [
            candidate
            for score, candidate in best_per_source.values()
            if score >= CONFLICT_MIN_CONFIDENCE
        ]
        if len({c.value for c in confident}) < 2:
            return fused

        preferred = min(confident, key=lambda c: _SOURCE_PRIORITY[c.source])
        return FusedField(
            value=preferred.value,
            confidence=CONTRADICTED_CONFIDENCE,
            source=preferred.source,
            needs_review=True,
            flags=(*fused.flags, FLAG_SOURCE_CONFLICT),
            agreement=False,
        )

    def _flag_card_mismatch(
        self,
        candidates: Mapping[FieldKey, list[Candidate]],
        result: dict[FieldKey, FusedField],
    ) -> None:
        """⭐ Rule 5 — the id read via QR disagrees with the one via MRZ.

        The strongest available signal that the two uploaded images are not the
        same card. Flagged, never acted on: blocking is `ValidationEngine`'s
        call (V-OCR-019), and this service does not decide blocking.
        """
        id_candidates = candidates.get(FieldKey.ID_NUMBER, [])
        qr_value = _first_value(id_candidates, FieldSource.QR)
        mrz_value = _first_value(id_candidates, FieldSource.MRZ)
        if qr_value is not None and mrz_value is not None and qr_value != mrz_value:
            result[FieldKey.ID_NUMBER] = result[FieldKey.ID_NUMBER].with_flag(
                FLAG_CARD_MISMATCH, confidence=CONTRADICTED_CONFIDENCE
            )

    def _check_id_consistency(
        self, result: dict[FieldKey, FusedField], context: FusionContext
    ) -> None:
        """⭐ Rule 6 — the id number encodes facts that must match the other fields.

        `001 1 99 012345` → province `001`, gender+century `1` (female, 1900s),
        birth year `99`. ⭐ **This catches a single misread digit in the middle
        of the number, which `^\\d{12}$` never can** — the kind of error that
        otherwise reaches a contract at full confidence.

        Only the birth-year and province halves are checkable here: gender is
        not one of the 6 extracted fields, so the gender cross-check belongs to
        V-OCR-022 where the form's value is available.
        """
        fused_id = result[FieldKey.ID_NUMBER]
        if fused_id.value is None:
            return
        try:
            citizen_id = CitizenId(fused_id.value)
        except ValidationError:  # a 12-digit shape is the VO's only requirement
            return

        if (
            context.known_province_codes
            and citizen_id.province_code not in context.known_province_codes
        ):
            result[FieldKey.ID_NUMBER] = fused_id.with_flag(
                FLAG_ID_INCONSISTENT, confidence=CONTRADICTED_CONFIDENCE
            )
            return

        birth_year = _year_of(result[FieldKey.DATE_OF_BIRTH].value)
        if birth_year is None:
            return
        if not _year_matches(citizen_id, birth_year):
            result[FieldKey.ID_NUMBER] = fused_id.with_flag(
                FLAG_ID_INCONSISTENT, confidence=CONTRADICTED_CONFIDENCE
            )


def _first_value(candidates: list[Candidate], source: FieldSource) -> str | None:
    return next((c.value for c in candidates if c.source is source and c.value), None)


def _year_of(iso_date: str | None) -> int | None:
    """The year of a normalized `YYYY-MM-DD` value, if it is one."""
    if iso_date is None or len(iso_date) < 4 or not iso_date[:4].isdigit():
        return None
    return int(iso_date[:4])


def _year_matches(citizen_id: CitizenId, birth_year: int) -> bool:
    """Both halves of the encoding: the century digit and the 2-digit year."""
    if f"{birth_year % 100:02d}" != citizen_id.birth_year_suffix:
        return False
    century = citizen_id.inferred_birth_year_range
    return century is None or century[0] <= birth_year <= century[1]
