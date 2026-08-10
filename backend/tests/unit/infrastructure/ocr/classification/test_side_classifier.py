"""`HeuristicSideClassifier` — the four signals and the four outcomes (§7.4.2).

Driven by stub channels so the reconciliation rules are exercised exactly, one
signal combination at a time.
"""
from __future__ import annotations

import numpy as np
import pytest

from cocas.domain.enums.card_side import CardSide
from cocas.domain.ports.ocr import (
    DocumentTypeSpec,
    QrExtractionResult,
    SideVerdict,
    TextRegion,
)
from cocas.infrastructure.ocr.classification import HeuristicSideClassifier
from cocas.infrastructure.ocr.classification import side_classifier as module
from cocas.infrastructure.ocr.preprocessing.image_data import NumpyImageData

from ..preprocessing.conftest import draw_card

FRONT_TITLE = "CONG HOAXAHOI CHU NGHIAVIET NAM\nCAN CU'O'C CONG DAN"
BACK_TITLE = "Dac diem nhan dang / Personal identification:"


class StubQr:
    def __init__(self, *, decodes: bool) -> None:
        self._decodes = decodes

    def decode(self, image_set):
        return QrExtractionResult(
            available=self._decodes, layout_recognized=self._decodes
        )


class StubRecognizer:
    """Answers with whatever text the card is supposed to be showing."""

    def __init__(self, text: str | None) -> None:
        self._text = text
        self.calls = 0

    def recognize_region(self, image, bbox, charset_hint):
        self.calls += 1
        if self._text is None:
            return None
        return TextRegion(bbox, self._text, 0.9)


class StubImageSet:
    """A card whose MRZ block is drawn, or not, where a real one would be."""

    def __init__(self, *, with_mrz_block: bool) -> None:
        self._array = _card(with_mrz_block=with_mrz_block)

    @property
    def v2(self):
        return NumpyImageData(self._array)

    @property
    def v3(self):
        return NumpyImageData(self._array)

    @property
    def warp_succeeded(self) -> bool:
        return True


def _card(*, with_mrz_block: bool) -> np.ndarray:
    """A synthetic card, reusing the fixture the transforms are tested against.

    ⭐ Drawn as runs of glyphs, not solid bars: `find_mrz_candidates` measures a
    morphological gradient, and a filled rectangle only produces edges at its
    top and bottom — too thin to register as a line of text.
    """
    return draw_card(with_mrz=with_mrz_block)


def doc_type(*, has_qr: bool = True, has_mrz: bool = True) -> DocumentTypeSpec:
    return DocumentTypeSpec(
        code="CCCD_CHIP",
        name="Căn cước công dân gắn chip",
        field_schema=[],
        zone_map={},
        anchor_patterns={},
        has_qr=has_qr,
        has_mrz=has_mrz,
        is_ocr_supported=True,
        expected_aspect_ratio=1.585,
    )


def classify(front_signals, back_signals, *, spec=None):
    """Build a classifier from two (qr, mrz_block, title) descriptions."""
    qr_a, mrz_a, title_a = front_signals
    qr_b, mrz_b, title_b = back_signals
    recognizer = StubRecognizer(title_a if title_a is not None else title_b)
    classifier = HeuristicSideClassifier(StubQr(decodes=qr_a or qr_b), recognizer)

    # Each image needs its own QR answer, so weigh them separately and rebuild.
    result_a = HeuristicSideClassifier(StubQr(decodes=qr_a), StubRecognizer(title_a))
    result_b = HeuristicSideClassifier(StubQr(decodes=qr_b), StubRecognizer(title_b))
    spec = spec or doc_type()
    evidence_a = result_a._weigh(StubImageSet(with_mrz_block=mrz_a), spec)
    evidence_b = result_b._weigh(StubImageSet(with_mrz_block=mrz_b), spec)
    return classifier, evidence_a, evidence_b


class TestSignals:
    def test_a_decodable_qr_argues_front(self):
        _, evidence, _ = classify((True, False, None), (False, False, None))
        assert evidence.front == pytest.approx(module.WEIGHT_QR)
        assert evidence.side.value == "FRONT"

    def test_an_mrz_block_low_on_the_card_argues_back(self):
        _, evidence, _ = classify((False, True, None), (False, False, None))
        assert evidence.back == pytest.approx(module.WEIGHT_MRZ)
        assert evidence.side.value == "BACK"

    def test_title_text_argues_when_nothing_else_does(self):
        _, evidence, _ = classify((False, False, FRONT_TITLE), (False, False, None))
        assert evidence.front == pytest.approx(module.WEIGHT_ANCHOR)

    def test_back_title_text_argues_back(self):
        _, evidence, _ = classify((False, False, BACK_TITLE), (False, False, None))
        assert evidence.back == pytest.approx(module.WEIGHT_ANCHOR)

    def test_no_evidence_means_no_side(self):
        _, evidence, _ = classify((False, False, None), (False, False, None))
        assert evidence.side is None

    def test_a_document_without_a_qr_never_spends_a_decode(self):
        spec = doc_type(has_qr=False)
        _, evidence, _ = classify((True, False, None), (False, False, None), spec=spec)
        assert evidence.front == 0.0


class TestLazyAnchors:
    """⭐ Recognizing the title band costs 41% of a whole-card pass. Measured on
    46 real photos, QR or the MRZ block settled 36 of them and the anchors never
    changed those verdicts — so they only run when nothing else decided."""

    def test_a_decisive_signal_skips_the_title_band(self):
        recognizer = StubRecognizer(FRONT_TITLE)
        classifier = HeuristicSideClassifier(StubQr(decodes=True), recognizer)
        classifier._weigh(StubImageSet(with_mrz_block=False), doc_type())
        assert recognizer.calls == 0

    def test_an_undecided_image_does_read_the_title_band(self):
        recognizer = StubRecognizer(FRONT_TITLE)
        classifier = HeuristicSideClassifier(StubQr(decodes=False), recognizer)
        classifier._weigh(StubImageSet(with_mrz_block=False), doc_type())
        assert recognizer.calls == 1

    def test_an_image_showing_both_qr_and_mrz_needs_no_anchor(self):
        """⭐ QR + MRZ on one image is a Căn cước 2024 back — decisive on its own.

        This test asserted the opposite until 2026-08-10 ("equal decisive scores
        decide nothing, so the anchors get a say"). Measuring the 2024 photos
        showed where that leads: the anchors are the 2021 generation's titles,
        so they say nothing about a 2024 card, and all 10 front/back pairs came
        back AMBIGUOUS after paying for a title-band pass.
        """
        recognizer = StubRecognizer(FRONT_TITLE)
        classifier = HeuristicSideClassifier(StubQr(decodes=True), recognizer)
        evidence = classifier._weigh(StubImageSet(with_mrz_block=True), doc_type())
        assert recognizer.calls == 0
        assert evidence.side is CardSide.BACK
        assert evidence.confidence == module.WEIGHT_QR_WITH_MRZ


class TestReconciliation:
    def test_front_then_back_resolves_without_swapping(self):
        classifier, a, b = classify((True, False, None), (False, True, None))
        assert module._reconcile(a, b) is SideVerdict.RESOLVED

    def test_back_then_front_is_detected_as_swapped(self):
        classifier, a, b = classify((False, True, None), (True, False, None))
        assert a.side.value == "BACK"
        assert module._reconcile(a, b) is SideVerdict.RESOLVED

    def test_two_confident_fronts_are_blocked_as_duplicates(self):
        _, a, b = classify((True, False, None), (True, False, None))
        assert module._reconcile(a, b) is SideVerdict.DUPLICATE_SIDE

    def test_one_confident_image_resolves_the_other_by_elimination(self):
        """⭐ The port's invariant is about BOTH images being weak. One certain
        side names the other, which is the common case for a front whose QR
        will not decode."""
        _, a, b = classify((False, True, None), (False, False, None))
        assert module._reconcile(a, b) is SideVerdict.RESOLVED

    def test_two_images_with_no_evidence_are_ambiguous(self):
        _, a, b = classify((False, False, None), (False, False, None))
        assert module._reconcile(a, b) is SideVerdict.AMBIGUOUS

    def test_a_weak_agreement_is_indecision_not_a_duplicate(self):
        """Blocking the upload deserves conviction from both images."""
        _, a, b = classify((True, False, None), (False, False, FRONT_TITLE))
        assert a.side is b.side
        assert module._reconcile(a, b) is SideVerdict.AMBIGUOUS

    def test_never_resolves_while_both_images_are_below_the_threshold(self):
        """⭐ The invariant `ICardSideClassifier` states outright."""
        _, a, b = classify((False, False, FRONT_TITLE), (False, False, BACK_TITLE))
        assert max(a.confidence, b.confidence) < module.ACCEPT_THRESHOLD
        assert module._reconcile(a, b) is SideVerdict.AMBIGUOUS


class TestClassifyResult:
    def test_reports_indices_and_the_swap_flag(self):
        classifier = HeuristicSideClassifier(StubQr(decodes=False), StubRecognizer(None))
        back = StubImageSet(with_mrz_block=True)
        front = StubImageSet(with_mrz_block=False)
        result = classifier.classify(back, front, doc_type())

        assert result.verdict is SideVerdict.RESOLVED
        assert result.swapped is True
        assert (result.front_index, result.back_index) == (1, 0)

    def test_keeps_the_signals_that_drove_the_decision(self):
        classifier = HeuristicSideClassifier(StubQr(decodes=False), StubRecognizer(None))
        result = classifier.classify(
            StubImageSet(with_mrz_block=False),
            StubImageSet(with_mrz_block=True),
            doc_type(),
        )
        assert result.signals["b"] == {"qr": False, "mrz_block": True}

    def test_a_dying_recognizer_is_reported_not_raised(self):
        class Exploding:
            def recognize_region(self, image, bbox, charset_hint):
                raise RuntimeError("engine died")

        classifier = HeuristicSideClassifier(StubQr(decodes=False), Exploding())
        result = classifier.classify(
            StubImageSet(with_mrz_block=False),
            StubImageSet(with_mrz_block=False),
            doc_type(),
        )
        assert result.verdict is SideVerdict.AMBIGUOUS
