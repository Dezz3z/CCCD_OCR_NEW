"""IssuePlaceNormalizer — 5-tier normalization to the 2 canonical issue places (§12.5).

⭐ The single most important invariant in this file: `normalize()` can only
ever return one of the two canonical strings, or `None`. There is no third
value, no matter what garbage comes in — tested exhaustively below with a
Hypothesis property test.

Evaluation order:
  Tier 1 — exact match after diacritics are stripped (no repository call)
  Tier 2 — exact match against `normalization_alias.alias_normalized`
  ⭐ Tier 5 — shape: which of the 2 the opening letters point at (`issue_place_shape`)
  Tier 3 — fuzzy match (`rapidfuzz.fuzz.token_set_ratio`) against the same aliases
  Tier 4 — keyword match against `match_tier=4` alias rows (all keywords present)
  no match — `None`, confidence 0.0

⚠️ **Tier 5 is numbered after tiers 3 and 4 but runs before them, and that is
deliberate.** The number is the provenance label a result carries to the UI and
the log; the order is what measurement dictates. Measured 2026-08-10 on the 22
real photos carrying this field, with all 16 seeded alias rows loaded:

| Tier | Correct | Confidence |
|---|---|---|
| 3 (fuzzy, whole string) | 13/22 | 0.65 · one at 0.90 |
| 4 (keywords) | 1/22 | 0.60 |
| **neither — no value at all** | **8/22** | — |
| ⭐ 5 (shape) | **22/22** | 0.92 |

The 8 failures are one defect seen twice: the recognizer merges words
(`CUCTRUONG CUCCANH SAT`), which empties `token_set_ratio`'s intersection and
breaks the keyword tier's all-present test at the same time. Both whole-string
tiers depend on the same token boundaries, so they fail *together* — they are
not the independent fallbacks the tier ladder implies. Tier 5 needs only the
first letters, which no merge disturbs.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from rapidfuzz import fuzz

from cocas.domain.ports.persistence import AliasRecord, IAliasRepository
from cocas.domain.services.issue_place_shape import discriminate
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
    """Domain Service — see module docstring for the 5-tier algorithm."""

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

        # ⭐ Tier 5 — the opening letters, before either whole-string tier gets a
        # turn. Both of those need the recognizer to have found the right word
        # boundaries; this one does not, and on the sample it is right where they
        # are silent (see the table in the module docstring).
        verdict = discriminate(raw)
        if verdict.value is not None:
            return NormalizationOutcome(value=verdict.value, confidence=verdict.confidence, tier=5)

        return (
            self._fuzzy_match(stripped, exact_candidates)
            or self._keyword_match(stripped, aliases)
            or NormalizationOutcome(value=None, confidence=0.0, tier=0)
        )

    @staticmethod
    def _fuzzy_match(
        stripped: str, exact_candidates: list[AliasRecord]
    ) -> NormalizationOutcome | None:
        """Tier 3 — fuzzy match against every diacritics-stripped alias.

        ⚠️ Depends on the recognizer having found the right word boundaries:
        `token_set_ratio` compares *sets of tokens*, so a merge like
        `CUCTRUONG CUCCANH SAT` empties the intersection and scores 56 on text
        a human reads at a glance. That is why tier 5 runs ahead of it.
        """
        best_alias: AliasRecord | None = None
        best_score = 0.0
        for alias in exact_candidates:
            normalized = alias.alias_normalized
            assert normalized is not None  # guaranteed by the exact_candidates filter above
            score = fuzz.token_set_ratio(stripped, normalized)
            if score > best_score:
                best_score = score
                best_alias = alias
        if best_alias is None or best_score < _FUZZY_LOW_THRESHOLD:
            return None
        confidence = (
            _FUZZY_HIGH_CONFIDENCE if best_score >= _FUZZY_HIGH_THRESHOLD else _FUZZY_LOW_CONFIDENCE
        )
        return NormalizationOutcome(
            value=best_alias.canonical_value,
            confidence=confidence,
            tier=3,
            matched_alias_id=best_alias.id,
        )

    @staticmethod
    def _keyword_match(
        stripped: str, aliases: Sequence[AliasRecord]
    ) -> NormalizationOutcome | None:
        """Tier 4 — every keyword present, in any order.

        ⚠️ All-or-nothing, and it fails on exactly the same input tier 3 does:
        the same merge that empties the intersection also removes the `CUC`
        token this test requires. Two tiers, one failure mode.
        """
        tokens = set(stripped.split())
        for alias in aliases:
            if alias.keywords and all(keyword in tokens for keyword in alias.keywords):
                return NormalizationOutcome(
                    value=alias.canonical_value,
                    confidence=_KEYWORD_CONFIDENCE,
                    tier=4,
                    matched_alias_id=alias.id,
                )
        return None
