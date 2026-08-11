"""`IDocumentTypeSelector` (Port 19) — which generation of card this is (§7.4.7).

Scores each candidate's `identity_markers` — the phrases printed on **exactly
one** generation — against text the recognizer has already produced, and picks
the type with strictly more hits.

⚠️ **The markers are not the anchor patterns, and reusing those instead is a
trap this project has already fallen into.** The two generations share most of
their boilerplate: `Full name`, `Date of birth`, `Date of expiry` and
`BỘ CÔNG AN` are declared as anchors by both, and worse, `Ngày, tháng, năm`
(2021) is a prefix of `Ngày, tháng, năm sinh` (2024) — the shared-prefix
cross-match of CLAUDE.md constraint 7. Counting anchor hits therefore measures
how legible the photo was, not which card it is.

⚠️ Same reason `CĂN CƯỚC` and `IDENTITY CARD` are absent from the 2024 marker
list even though they are its printed titles: measured over the whole sample,
`CĂN CƯỚC CÔNG DÂN` scores 100 against `CĂN CƯỚC`, so a card of either
generation matches both and the vote ties on every 2021 front.

⭐ A marker list is **data on the document type row**, so a third document type
is a row, not a branch here (NFR-10, P-06).
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from loguru import logger

from cocas.infrastructure.ocr.text_matching import similarity

if TYPE_CHECKING:
    from cocas.domain.ports.ocr import DocumentTypeSpec, TextRegion

# ⭐ 85, not `FIELD_ANCHOR_THRESHOLD`'s 75. Field anchors match short damaged
# label fragments and can afford to be generous; a generation verdict rewrites
# the whole `zone_map`, and a wrong zone map yields confident wrong values
# rather than missing ones (§7.9). Measured on the sample at this threshold.
MARKER_THRESHOLD = 85.0


class MarkerDocumentTypeSelector:
    """Port 19 — see the module docstring."""

    def select(
        self,
        regions: list[TextRegion],
        candidates: Sequence[DocumentTypeSpec],
    ) -> DocumentTypeSpec | None:
        """The candidate with strictly the most marker hits, or None.

        ⭐ Returning `None` on a tie is the whole safety argument: the caller
        then keeps whatever the session declared, which is at worst as wrong as
        not asking. Breaking ties by order would turn "no evidence" into a
        silent vote for whichever row happened to be listed first.
        """
        if len(candidates) < 2:
            return candidates[0] if candidates else None

        lines = [region.text for region in regions if region.text.strip()]
        if not lines:
            return None

        scored = [(_hits(lines, spec), spec) for spec in candidates]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        best_hits, best = scored[0]
        runner_up_hits = scored[1][0]

        if best_hits == 0 or best_hits == runner_up_hits:
            logger.debug(
                "Document type not separable from recognized text",
                best=best.code,
                best_hits=best_hits,
                runner_up_hits=runner_up_hits,
                lines=len(lines),
            )
            return None
        return best


def _hits(lines: Sequence[str], spec: DocumentTypeSpec) -> int:
    """How many of this type's own markers appear in the recognized text.

    Counts *markers matched*, not lines matched: a card that prints one phrase
    on both sides must not out-score a card that prints two different ones.
    """
    return sum(
        1
        for marker in spec.identity_markers
        if any(similarity(line, marker) >= MARKER_THRESHOLD for line in lines)
    )
