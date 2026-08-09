"""FieldFusionService — merges QR/MRZ/OCR candidates into one value per field (§12.6).

⭐ P-04 lives here: extraction is never "just OCR" — every field's final
value is the outcome of fusing up to three independent channels.

This is a first-pass, clearly-scoped scoring heuristic (source priority +
a consensus bonus), not a tuned model — §14.5 flags real calibration as a
P2 activity that needs the Golden Set, which does not exist yet. What *is*
fixed now are the invariants the spec makes non-negotiable: all 6 keys
present, confidence always in [0, 1], `value is None ⇒ confidence == 0 and
source == NONE`, and cross-channel conflicts surfaced as flags rather than
silently resolved.
"""
from __future__ import annotations

from dataclasses import dataclass

from cocas.domain.enums.field_key import FieldKey
from cocas.domain.enums.field_source import FieldSource

CONSENSUS_BONUS = 0.05
MAX_CONFIDENCE = 1.0
DEFAULT_REVIEW_THRESHOLD = 0.85
CONFLICT_SCORE_GAP = 0.15

_SOURCE_PRIORITY: dict[FieldSource, int] = {
    FieldSource.QR: 0,
    FieldSource.MRZ: 1,
    FieldSource.OCR: 2,
    FieldSource.MANUAL: 3,
    FieldSource.NONE: 4,
}


@dataclass(frozen=True, slots=True)
class Candidate:
    """One channel's already-normalized value for a field."""

    value: str | None
    source: FieldSource
    confidence: float


@dataclass(frozen=True, slots=True)
class FusionContext:
    """Tuning passed into `fuse()` — kept minimal on purpose (P-10)."""

    review_threshold: float = DEFAULT_REVIEW_THRESHOLD


@dataclass(frozen=True, slots=True)
class FusedField:
    """The winning value for one field, plus how confident and how it was chosen."""

    value: str | None
    confidence: float
    source: FieldSource
    needs_review: bool
    flags: tuple[str, ...] = ()


class FieldFusionService:
    """Domain Service — see module docstring for the scoring approach."""

    def fuse(
        self, candidates: dict[FieldKey, list[Candidate]], context: FusionContext
    ) -> dict[FieldKey, FusedField]:
        result: dict[FieldKey, FusedField] = {}
        for key in FieldKey:
            result[key] = self._fuse_field(candidates.get(key, []), context)
        self._flag_card_mismatch(candidates, result)
        return result

    def _fuse_field(self, field_candidates: list[Candidate], context: FusionContext) -> FusedField:
        usable = [c for c in field_candidates if c.value is not None]
        if not usable:
            return FusedField(value=None, confidence=0.0, source=FieldSource.NONE, needs_review=True)

        # One best candidate per source (highest confidence wins a source's slot).
        best_per_source: dict[FieldSource, Candidate] = {}
        for candidate in usable:
            current = best_per_source.get(candidate.source)
            if current is None or candidate.confidence > current.confidence:
                best_per_source[candidate.source] = candidate

        # Consensus: how many distinct sources agree on each value.
        agreement: dict[str, int] = {}
        for candidate in best_per_source.values():
            assert candidate.value is not None
            agreement[candidate.value] = agreement.get(candidate.value, 0) + 1

        scored: list[tuple[float, int, Candidate]] = []
        for candidate in best_per_source.values():
            assert candidate.value is not None
            bonus = CONSENSUS_BONUS * (agreement[candidate.value] - 1)
            score = min(candidate.confidence + bonus, MAX_CONFIDENCE)
            scored.append((score, _SOURCE_PRIORITY[candidate.source], candidate))

        # Highest score wins; ties broken by source priority (lower = better).
        scored.sort(key=lambda item: (-item[0], item[1]))
        winning_score, _, winner = scored[0]

        flags: list[str] = []
        if len(scored) > 1:
            runner_up_score = scored[1][0]
            runner_up = scored[1][2]
            if (
                winning_score - runner_up_score < CONFLICT_SCORE_GAP
                and winner.value != runner_up.value
            ):
                flags.append("SOURCE_CONFLICT")

        needs_review = winning_score < context.review_threshold
        return FusedField(
            value=winner.value,
            confidence=winning_score,
            source=winner.source,
            needs_review=needs_review,
            flags=tuple(flags),
        )

    def _flag_card_mismatch(
        self,
        candidates: dict[FieldKey, list[Candidate]],
        result: dict[FieldKey, FusedField],
    ) -> None:
        """⭐ CARD_MISMATCH: the id_number read via QR disagrees with the one via MRZ —
        the strongest signal the two uploaded images may not be the same card.
        """
        id_candidates = candidates.get(FieldKey.ID_NUMBER, [])
        qr_value = next((c.value for c in id_candidates if c.source == FieldSource.QR), None)
        mrz_value = next((c.value for c in id_candidates if c.source == FieldSource.MRZ), None)
        if qr_value is not None and mrz_value is not None and qr_value != mrz_value:
            fused = result[FieldKey.ID_NUMBER]
            result[FieldKey.ID_NUMBER] = FusedField(
                value=fused.value,
                confidence=fused.confidence,
                source=fused.source,
                needs_review=True,
                flags=(*fused.flags, "CARD_MISMATCH"),
            )
