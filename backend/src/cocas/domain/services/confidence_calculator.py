"""ConfidenceCalculator — rule 7 of S10: one number for the whole card (§7.2 D4, §03 S10).

Split out from `FieldFusionService` because it answers a different question.
Fusion asks "which reading of this field wins"; this asks "how much of the card
did we actually read", which is what the UI turns into a green/amber/red banner
and what ALT-03 thresholds on (`overall < 0.40` ⇒ "chụp lại").

⭐ The weights are **not** an average. `id_number` is worth three times
`issue_place` because getting it wrong means the contract names the wrong
person, while a missing issue place is one dropdown the user picks from two
options. The table is §03 S10 rule 7, unchanged.
"""
from __future__ import annotations

from collections.abc import Mapping

from cocas.domain.enums.field_key import FieldKey
from cocas.domain.services.field_fusion_service import FusedField

# Sums to exactly 1.00 — asserted below rather than trusted, because a table
# that quietly stops summing to 1 turns every score into a silent underestimate.
FIELD_WEIGHTS: Mapping[FieldKey, float] = {
    FieldKey.ID_NUMBER: 0.30,
    FieldKey.FULL_NAME: 0.25,
    FieldKey.DATE_OF_BIRTH: 0.15,
    FieldKey.ISSUE_DATE: 0.10,
    FieldKey.EXPIRY_DATE: 0.10,
    FieldKey.ISSUE_PLACE: 0.10,
}

assert abs(sum(FIELD_WEIGHTS.values()) - 1.0) < 1e-9, "FIELD_WEIGHTS must sum to 1.00"

# ALT-03: below this, the honest advice is "take the photo again" rather than
# "correct these six fields".
RETAKE_THRESHOLD = 0.40


class ConfidenceCalculator:
    """Domain Service — rule 7 of the fusion rules."""

    def overall(self, fields: Mapping[FieldKey, FusedField]) -> float:
        """The weighted mean confidence across all 6 fields, always in [0, 1].

        ⭐ A field that was not read counts as 0, it is not excluded. Dropping
        missing fields from the denominator would score a card where only the
        id number was read at 1.00 — "perfectly read", from one field out of six.
        """
        total = 0.0
        for key, weight in FIELD_WEIGHTS.items():
            fused = fields.get(key)
            if fused is not None and fused.value is not None:
                total += weight * min(max(fused.confidence, 0.0), 1.0)
        return round(total, 4)

    def needs_retake(self, fields: Mapping[FieldKey, FusedField]) -> bool:
        """ALT-03 — the read is poor enough that a better photo beats correcting it."""
        return self.overall(fields) < RETAKE_THRESHOLD
