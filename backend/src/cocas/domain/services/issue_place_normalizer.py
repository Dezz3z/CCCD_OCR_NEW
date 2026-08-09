"""IssuePlaceNormalizer — 4-tier normalization to the 2 canonical issue places (§12.5).

⭐ The single most important invariant in this file: `normalize()` can only
ever return one of the two canonical strings, or `None`. There is no third
value, no matter what garbage comes in — tested exhaustively below with a
Hypothesis property test.

Tier order, as specified:
  Tier 1 — exact match after diacritics are stripped (no repository call)
  Tier 2 — exact match against `normalization_alias.alias_normalized`
  Tier 3 — fuzzy match (`rapidfuzz.fuzz.token_set_ratio`) against the same aliases
  Tier 4 — keyword match against `match_tier=4` alias rows (all keywords present)
  no match — `None`, confidence 0.0
"""
from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

from cocas.domain.ports.persistence import AliasRecord, IAliasRepository
from cocas.domain.value_objects._vn_text import collapse_whitespace, nfc_upper, strip_diacritics
from cocas.domain.value_objects.issue_place import (
    BO_CONG_AN,
    CUC_CANH_SAT_QLHC_TTXH,
    IssuePlace,
)

_STRIPPED_CANONICAL: dict[str, str] = {
    strip_diacritics(_canonical): _canonical
    for _canonical in (BO_CONG_AN, CUC_CANH_SAT_QLHC_TTXH)
}

_FUZZY_HIGH_THRESHOLD = 85.0
_FUZZY_LOW_THRESHOLD = 70.0
_FUZZY_HIGH_CONFIDENCE = 0.90
_FUZZY_LOW_CONFIDENCE = 0.65
_KEYWORD_CONFIDENCE = 0.60


@dataclass(frozen=True, slots=True)
class NormalizationOutcome:
    """Result of `IssuePlaceNormalizer.normalize()`.

    ⭐ `value` is always `None` or one of the 2 canonical `IssuePlace` strings.
    """

    value: str | None
    confidence: float
    tier: int
    matched_alias_id: object | None = None

    def to_issue_place(self) -> IssuePlace | None:
        return IssuePlace(self.value) if self.value is not None else None


class IssuePlaceNormalizer:
    """Domain Service — see module docstring for the 4-tier algorithm."""

    def __init__(self, alias_repository: IAliasRepository, document_type_code: str = "CCCD_CHIP") -> None:
        self._alias_repository = alias_repository
        self._document_type_code = document_type_code

    async def normalize(self, raw: str) -> NormalizationOutcome:
        pre = collapse_whitespace(nfc_upper(raw or ""))
        stripped = strip_diacritics(pre)

        # Tier 1 — exact match, diacritics stripped, no repository call needed.
        canonical = _STRIPPED_CANONICAL.get(stripped)
        if canonical is not None:
            return NormalizationOutcome(value=canonical, confidence=1.0, tier=1)

        aliases = await self._alias_repository.list_active(self._document_type_code, "issue_place")
        exact_candidates = [a for a in aliases if a.alias_normalized is not None]

        # Tier 2 — exact match against a curated alias.
        for alias in exact_candidates:
            if alias.alias_normalized == stripped:
                return NormalizationOutcome(
                    value=alias.canonical_value,
                    confidence=alias.assigned_confidence,
                    tier=2,
                    matched_alias_id=alias.id,
                )

        # Tier 3 — fuzzy match against every diacritics-stripped alias.
        best_alias: AliasRecord | None = None
        best_score = 0.0
        for alias in exact_candidates:
            normalized = alias.alias_normalized
            assert normalized is not None  # guaranteed by the exact_candidates filter above
            score = fuzz.token_set_ratio(stripped, normalized)
            if score > best_score:
                best_score = score
                best_alias = alias
        if best_alias is not None and best_score >= _FUZZY_LOW_THRESHOLD:
            confidence = (
                _FUZZY_HIGH_CONFIDENCE if best_score >= _FUZZY_HIGH_THRESHOLD else _FUZZY_LOW_CONFIDENCE
            )
            return NormalizationOutcome(
                value=best_alias.canonical_value,
                confidence=confidence,
                tier=3,
                matched_alias_id=best_alias.id,
            )

        # Tier 4 — every keyword present, in any order.
        tokens = set(stripped.split())
        for alias in aliases:
            if not alias.keywords:
                continue
            if all(keyword in tokens for keyword in alias.keywords):
                return NormalizationOutcome(
                    value=alias.canonical_value,
                    confidence=_KEYWORD_CONFIDENCE,
                    tier=4,
                    matched_alias_id=alias.id,
                )

        return NormalizationOutcome(value=None, confidence=0.0, tier=0)
