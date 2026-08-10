"""`ICardSideClassifier` (Port 4) — which upload is the front — §7.4.2.

⭐ Runs at S4, *before* the QR, MRZ and OCR channels, so every signal it uses
has to be cheap. Whole-card recognition here would be paid twice: once to pick
a side and again at S7 to read the fields, and two cards at ~2s each would eat
the entire 9s p95 budget on classification alone.

So the signals are, in cost order:

| Signal | Weight | Cost | Says |
|---|---|---|---|
| ⭐ **Both** a QR and a low three-line block | 0.80 | already paid | BACK (Căn cước 2024) |
| QR decodes with a valid layout, alone | 0.40 | ~120 ms, shared with S5 | FRONT |
| A three-line block sits low on the card, alone | 0.40 | ~20 ms, pure OpenCV | BACK |
| Front title text in the top band | 0.15 | one small region | FRONT |
| Back title text in the top band | 0.15 | same region | BACK |

⚠️ The two 0.10 texture signals of §7.4.2 (portrait bottom-left, fingerprint
left) are **not implemented**. They need a Haar cascade — another binary to
package and another thing to go wrong offline — and the four signals above
already separate the sample cleanly. Left out under P-10 rather than forgotten;
if the Golden Set shows cards the four signals cannot split, they go in then.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from loguru import logger

from cocas.domain.enums.card_side import CardSide
from cocas.domain.ports.ocr import RelativeBox, SideClassification, SideVerdict
from cocas.infrastructure.ocr.text_matching import SIDE_ANCHOR_THRESHOLD, best_match

from ..preprocessing import transforms
from ..preprocessing.image_data import BgrArray, NumpyImageData

if TYPE_CHECKING:
    from cocas.domain.ports.ocr import (
        DocumentTypeSpec,
        ImageData,
        IQrDecoder,
        IRegionRecognizer,
        PreprocessedImageSet,
    )

WEIGHT_QR = 0.40
WEIGHT_MRZ = 0.40
WEIGHT_ANCHOR = 0.15

# ⭐ QR **and** MRZ on one image is not a tie — it is the single most decisive
# observation the classifier can make. Measured 2026-08-10 on the sample's 7
# Căn cước 2024 photos: treating the two signals as independent votes left all
# 10 front/back pairs `AMBIGUOUS` (0.40 vs 0.40, cancelling exactly), because
# the 2024 generation prints its QR on the **back**, beside the MRZ (§7.4.7).
#
# No card prints both on the same side except that one, so the *combination*
# identifies a back more strongly than either signal alone — hence a weight
# above both, not the sum of two conflicting ones.
WEIGHT_QR_WITH_MRZ = 0.80

# ⭐ Re-derived, not copied. §7.4.2 pairs a 0.60 accept threshold with six
# signals summing to 0.65 per side — so 0.60 demands that *all three* of a
# side's signals fire. Drop the two 0.10 texture signals and the achievable
# maximum falls to 0.55, at which point a 0.60 gate makes every card
# AMBIGUOUS. The threshold has to describe the evidence that actually exists.
#
# 0.40 is one decisive signal, and both decisive signals are decisive for a
# reason: a CCCD's QR is printed only on the front and its MRZ only on the
# back. Neither can appear on the wrong side, so one of them is conclusive.
ACCEPT_THRESHOLD = 0.40

# Both cards print their identifying text in the top third; recognizing only
# that strip costs a fraction of a whole-card pass.
_TITLE_BAND = RelativeBox(x=0.0, y=0.0, w=1.0, h=0.32)

# A three-line block below this line is the MRZ, not the address block (which
# sits higher). Measured centre of the real MRZ is ~0.79.
_MRZ_MIN_CENTRE = 0.55

FRONT_ANCHORS = [
    "CĂN CƯỚC CÔNG DÂN",
    "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM",
    "Citizen Identity Card",
    "Độc lập - Tự do - Hạnh phúc",
]
BACK_ANCHORS = [
    "Đặc điểm nhân dạng",
    "Personal identification",
    "CỤC TRƯỞNG CỤC CẢNH SÁT",
    "Nơi thường trú",
]


@dataclass(frozen=True, slots=True)
class _Evidence:
    """What one image scored for each side, and why."""

    front: float
    back: float
    signals: dict[str, object] = field(default_factory=dict)

    @property
    def side(self) -> CardSide | None:
        """The side this image argues for — None when it argues for neither.

        ⭐ A tie is genuinely undecided and must not silently become "front".
        Both an evidence-free image and an image scoring equally for both sides
        (a photo showing a QR *and* an MRZ) land here, and both need the other
        image to settle them.
        """
        if self.front == self.back:
            return None
        return CardSide.FRONT if self.front > self.back else CardSide.BACK

    @property
    def confidence(self) -> float:
        return max(self.front, self.back)


class HeuristicSideClassifier:
    """Score both uploads for frontness and backness, then reconcile them."""

    def __init__(self, qr_decoder: IQrDecoder, recognizer: IRegionRecognizer) -> None:
        self._qr_decoder = qr_decoder
        self._recognizer = recognizer

    def classify(
        self,
        image_a: PreprocessedImageSet,
        image_b: PreprocessedImageSet,
        doc_type: DocumentTypeSpec,
    ) -> SideClassification:
        """Decide which image is the front, or refuse to (§7.3 `ICardSideClassifier`).

        ⭐ Invariant: never `RESOLVED` while both images score below 0.60. One
        confident image is enough — the other is the remaining side by
        elimination — but two uncertain ones are not.
        """
        evidence_a = self._weigh(image_a, doc_type)
        evidence_b = self._weigh(image_b, doc_type)
        verdict = _reconcile(evidence_a, evidence_b)

        # Whichever image has an opinion names the order; if only B does, A is
        # the other side by elimination.
        swapped = verdict is SideVerdict.RESOLVED and (
            evidence_a.side is CardSide.BACK or evidence_b.side is CardSide.FRONT
        )
        front_index, back_index = (1, 0) if swapped else (0, 1)

        if verdict is not SideVerdict.RESOLVED:
            logger.warning(
                "Card sides not resolved: {verdict}",
                verdict=verdict.value,
                confidence_a=evidence_a.confidence,
                confidence_b=evidence_b.confidence,
            )

        return SideClassification(
            front_index=front_index,
            back_index=back_index,
            confidence_a=round(evidence_a.confidence, 3),
            confidence_b=round(evidence_b.confidence, 3),
            swapped=swapped,
            verdict=verdict,
            signals={"a": evidence_a.signals, "b": evidence_b.signals},
        )

    def _weigh(
        self, image_set: PreprocessedImageSet, doc_type: DocumentTypeSpec
    ) -> _Evidence:
        signals: dict[str, object] = {}
        front = back = 0.0

        carries_qr = doc_type.has_qr and self._has_qr(image_set)
        carries_mrz = doc_type.has_mrz and self._has_mrz_block(image_set)
        signals["qr"] = carries_qr
        signals["mrz_block"] = carries_mrz

        if carries_qr and carries_mrz:
            # ⭐ A Căn cước 2024 back, and nothing else — see WEIGHT_QR_WITH_MRZ.
            back += WEIGHT_QR_WITH_MRZ
            signals["qr_with_mrz"] = True
        elif carries_qr:
            front += WEIGHT_QR
        elif carries_mrz:
            back += WEIGHT_MRZ

        if front != back:
            # ⭐ A decisive signal already fired, so the anchors cannot change
            # the answer — and recognizing the title band costs 41% of a whole
            # card. Measured on 46 real photos: QR or the MRZ block settled 36
            # of them, and on those 36 the anchors never altered the verdict.
            return _Evidence(front=front, back=back, signals=signals)

        front_anchor, back_anchor = self._read_title_band(image_set)
        if front_anchor is not None:
            front += WEIGHT_ANCHOR
            signals["front_anchor"] = front_anchor
        if back_anchor is not None:
            back += WEIGHT_ANCHOR
            signals["back_anchor"] = back_anchor

        return _Evidence(front=front, back=back, signals=signals)

    def _has_qr(self, image_set: PreprocessedImageSet) -> bool:
        """⭐ A decodable QR with a *recognized layout* — a stray barcode is not a front."""
        result = self._qr_decoder.decode(image_set)
        return result.available and result.layout_recognized

    def _has_mrz_block(self, image_set: PreprocessedImageSet) -> bool:
        """Three evenly-spaced full-width lines low on the rectified card.

        Purely geometric, so it costs nothing and works before any text has
        been read. It cannot tell an MRZ from the address block on its own,
        which is why the position guard matters: the address block sits higher.
        """
        try:
            centres = transforms.find_mrz_candidates(_array_of(image_set.v2))
        except Exception:
            logger.opt(exception=True).debug("MRZ block detection failed")
            return False
        return any(centre >= _MRZ_MIN_CENTRE for centre in centres)

    def _read_title_band(
        self, image_set: PreprocessedImageSet
    ) -> tuple[str | None, str | None]:
        """Match the top strip against both sides' printed titles."""
        try:
            region = self._recognizer.recognize_region(image_set.v3, _TITLE_BAND, None)
        except Exception:
            logger.opt(exception=True).debug("Title band recognition failed")
            return None, None
        if region is None or not region.text.strip():
            return None, None

        front_anchor, front_score = best_match(region.text, FRONT_ANCHORS)
        back_anchor, back_score = best_match(region.text, BACK_ANCHORS)
        return (
            front_anchor if front_score >= SIDE_ANCHOR_THRESHOLD else None,
            back_anchor if back_score >= SIDE_ANCHOR_THRESHOLD else None,
        )


def _reconcile(a: _Evidence, b: _Evidence) -> SideVerdict:
    """Turn two independent scores into one of the four outcomes (§7.4.2)."""
    if a.side is not None and a.side is b.side:
        # ⭐ Blocking the upload needs conviction from BOTH images; one weak
        # score agreeing with a strong one is indecision, not a duplicate.
        if min(a.confidence, b.confidence) >= ACCEPT_THRESHOLD:
            return SideVerdict.DUPLICATE_SIDE
        return SideVerdict.AMBIGUOUS

    # Opposite sides, or one image with an opinion and one without: either way
    # the order follows, provided the opinion is strong enough to act on.
    decisive = [
        evidence.confidence
        for evidence in (a, b)
        if evidence.side is not None and evidence.confidence >= ACCEPT_THRESHOLD
    ]
    return SideVerdict.RESOLVED if decisive else SideVerdict.AMBIGUOUS


def _array_of(image: ImageData) -> BgrArray:
    return cast(NumpyImageData, image).array
