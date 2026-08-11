"""Tests for `ExtractionPipeline` (§12.3) — the 9 stages, and the promises about them.

⭐ Everything here runs on `fake_ports.py` alone: no images, no PaddleOCR, no
database. That is §12.2's acceptance criterion, and it is also why these tests
can assert things a real run cannot — like "the engine was called exactly once".
"""
from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from cocas.application.dto.extraction import ExtractionResult
from cocas.application.pipelines.extraction_pipeline import (
    CORROBORATION_FLOOR,
    ExtractionPipeline,
    _fields_printed_on,
    _sides_worth_reading,
)
from cocas.domain.enums.card_side import CardSide
from cocas.domain.enums.field_key import FieldKey
from cocas.domain.enums.field_source import FieldSource
from cocas.domain.enums.ocr_session_status import OcrSessionStatus
from cocas.domain.exceptions import (
    ImageDecodeError,
    OcrEngineUnavailableError,
    OcrTimeoutError,
)
from cocas.domain.ports.ocr import (
    DocumentTypeSpec,
    ExtractionStrategy,
    MrzExtractionResult,
    QrExtractionResult,
    RawFieldValue,
    RelativeBox,
    SideClassification,
    SideVerdict,
    TextRegion,
)
from cocas.domain.services.field_fusion_service import Candidate
from cocas.domain.services.field_normalizer import FieldNormalizer
from cocas.domain.services.issue_place_normalizer import IssuePlaceNormalizer
from cocas.domain.value_objects.issue_place import BO_CONG_AN
from tests.fixtures.fake_ports import (
    FakeAliasRepository,
    FakeCardSideClassifier,
    FakeDocumentTypeSelector,
    FakeFieldExtractor,
    FakeImagePreprocessor,
    FakeMrzReader,
    FakeOcrEngine,
    FakeQrDecoder,
    FrozenClock,
    NullOcrEngine,
)

# --------------------------------------------------------------------------
# Fixtures — a card, its two document types, and a working set of channels
# --------------------------------------------------------------------------

ID_NUMBER = "001199012345"
FULL_NAME = "NGUYỄN VĂN AN"
BIRTH_DATE = "1999-05-14"
ISSUE_DATE = "2021-08-20"
EXPIRY_DATE = "2044-05-14"

# ⭐ The real seeded shape: a flat map whose entries name their own side. Lever 2
# reads it, so a test that flattens it differently tests nothing.
ZONE_MAP_2021 = {
    "id_number": {"x": 0.26, "y": 0.37, "w": 0.54, "h": 0.15, "side": "FRONT"},
    "full_name": {"x": 0.26, "y": 0.51, "w": 0.55, "h": 0.14, "side": "FRONT"},
    "date_of_birth": {"x": 0.28, "y": 0.58, "w": 0.53, "h": 0.13, "side": "FRONT"},
    "expiry_date": {"x": 0.00, "y": 0.85, "w": 0.40, "h": 0.14, "side": "FRONT"},
    "issue_date": {"x": 0.00, "y": 0.08, "w": 0.57, "h": 0.17, "side": "BACK"},
    "issue_place": {"x": 0.13, "y": 0.13, "w": 0.44, "h": 0.16, "side": "BACK"},
    "mrz": {"x": 0.02, "y": 0.62, "w": 0.96, "h": 0.36, "side": "BACK"},
}

# The 2024 generation moves the expiry date to the back (§7.4.7).
ZONE_MAP_2024 = {
    "id_number": {"x": 0.26, "y": 0.40, "w": 0.54, "h": 0.12, "side": "FRONT"},
    "full_name": {"x": 0.26, "y": 0.52, "w": 0.55, "h": 0.12, "side": "FRONT"},
    "date_of_birth": {"x": 0.28, "y": 0.60, "w": 0.53, "h": 0.11, "side": "FRONT"},
    "issue_date": {"x": 0.00, "y": 0.08, "w": 0.57, "h": 0.14, "side": "BACK"},
    "expiry_date": {"x": 0.00, "y": 0.20, "w": 0.57, "h": 0.14, "side": "BACK"},
    "issue_place": {"x": 0.13, "y": 0.30, "w": 0.44, "h": 0.16, "side": "BACK"},
    "mrz": {"x": 0.02, "y": 0.62, "w": 0.96, "h": 0.36, "side": "BACK"},
}


def doc_type(code: str = "CCCD_CHIP", zone_map: dict[str, object] | None = None,
             **overrides: object) -> DocumentTypeSpec:
    defaults: dict[str, object] = {
        "code": code,
        "name": code,
        "field_schema": [],
        "zone_map": zone_map if zone_map is not None else dict(ZONE_MAP_2021),
        "anchor_patterns": {},
        "has_qr": True,
        "has_mrz": True,
        "is_ocr_supported": True,
        "expected_aspect_ratio": 1.585,
    }
    defaults.update(overrides)
    return DocumentTypeSpec(**defaults)  # type: ignore[arg-type]


CCCD_2021 = doc_type()
CAN_CUOC_2024 = doc_type("CAN_CUOC_2024", ZONE_MAP_2024)


def qr_result(**overrides: object) -> QrExtractionResult:
    fields = {
        FieldKey.ID_NUMBER: ID_NUMBER,
        FieldKey.FULL_NAME: FULL_NAME,
        FieldKey.DATE_OF_BIRTH: "14051999",
        FieldKey.ISSUE_DATE: "20082021",
    }
    defaults: dict[str, object] = {
        "available": True,
        "raw_payload": "…",
        "fields": fields,
        "layout_recognized": True,
        "attempts": 1,
    }
    defaults.update(overrides)
    return QrExtractionResult(**defaults)  # type: ignore[arg-type]


def mrz_result(**overrides: object) -> MrzExtractionResult:
    defaults: dict[str, object] = {
        "available": True,
        "raw_lines": ["…", "…", "…"],
        "fields": {
            FieldKey.ID_NUMBER: ID_NUMBER,
            FieldKey.DATE_OF_BIRTH: "14051999",
            FieldKey.EXPIRY_DATE: "14052044",
        },
        "checksum_valid": True,
        "corrections_applied": 0,
        "confidence": 0.98,
    }
    defaults.update(overrides)
    return MrzExtractionResult(**defaults)  # type: ignore[arg-type]


def region(text: str, y: float = 0.5, confidence: float = 0.95) -> TextRegion:
    return TextRegion(
        bbox=RelativeBox(x=0.1, y=y, w=0.5, h=0.06), text=text, confidence=confidence
    )


def raw(text: str, confidence: float = 0.93) -> RawFieldValue:
    return RawFieldValue(
        text=text,
        confidence=confidence,
        bbox=RelativeBox(x=0.1, y=0.2, w=0.4, h=0.05),
        strategy=ExtractionStrategy.ZONE,
    )


def build(
    *,
    qr: QrExtractionResult | None = None,
    mrz: MrzExtractionResult | None = None,
    engine: FakeOcrEngine | None = None,
    extractor: FakeFieldExtractor | None = None,
    classification: SideClassification | None = None,
    preprocessor: FakeImagePreprocessor | None = None,
    selector: FakeDocumentTypeSelector | None = None,
) -> ExtractionPipeline:
    """A pipeline whose every collaborator is a fake, wired the way P3 wires it."""
    return ExtractionPipeline(
        preprocessor=preprocessor or FakeImagePreprocessor(),
        side_classifier=FakeCardSideClassifier(classification),
        qr_decoder=FakeQrDecoder(qr if qr is not None else QrExtractionResult(available=False)),
        mrz_reader=FakeMrzReader(
            mrz if mrz is not None else MrzExtractionResult(available=False)
        ),
        engine=engine or FakeOcrEngine([region("CĂN CƯỚC CÔNG DÂN", y=0.1)]),
        extractor=extractor or FakeFieldExtractor(),
        doc_type_selector=selector or FakeDocumentTypeSelector(),
        normalizer=FieldNormalizer(IssuePlaceNormalizer(FakeAliasRepository())),
        clock=FrozenClock(datetime(2026, 8, 11, tzinfo=UTC)),
    )


async def run(pipeline: ExtractionPipeline, **kwargs: object) -> ExtractionResult:
    return await pipeline.execute(b"front-bytes", b"back-bytes", [CCCD_2021], **kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------


class TestPostconditions:
    """§12.3's three structural promises, on the happy path and every other."""

    async def test_all_six_field_keys_are_present_after_a_clean_run(self) -> None:
        result = await run(build(qr=qr_result(), mrz=mrz_result()))
        assert set(result.fields) == set(FieldKey)

    async def test_all_six_field_keys_are_present_when_every_channel_is_dead(self) -> None:
        result = await run(build(engine=NullOcrEngine()))
        assert set(result.fields) == set(FieldKey)
        assert result.fields_read == 0

    async def test_status_is_always_one_the_pipeline_may_produce(self) -> None:
        for pipeline in (
            build(qr=qr_result(), mrz=mrz_result()),
            build(engine=NullOcrEngine()),
        ):
            result = await run(pipeline)
            assert result.status in {
                OcrSessionStatus.COMPLETED,
                OcrSessionStatus.COMPLETED_WITH_WARNINGS,
                OcrSessionStatus.NEEDS_REUPLOAD,
                OcrSessionStatus.NEEDS_MANUAL_ASSIGN,
                OcrSessionStatus.FAILED,
            }

    async def test_error_code_is_set_exactly_when_the_run_failed(self) -> None:
        ok = await run(build(qr=qr_result()))
        assert ok.error_code is None

        preprocessor = FakeImagePreprocessor()
        preprocessor.prepare = _raises(ImageDecodeError("hỏng"))  # type: ignore[method-assign]
        failed = await run(build(preprocessor=preprocessor))
        assert failed.status is OcrSessionStatus.FAILED
        assert failed.error_code == "IMAGE_DECODE_ERROR"

    async def test_duration_is_recorded_even_on_the_failure_path(self) -> None:
        preprocessor = FakeImagePreprocessor()
        preprocessor.prepare = _raises(ImageDecodeError("hỏng"))  # type: ignore[method-assign]
        result = await run(build(preprocessor=preprocessor))
        assert result.duration_ms >= 0


class TestNeverRaises:
    """⭐ The invariant that keeps the job worker alive (§12.3, §7.7)."""

    async def test_a_preprocessor_that_explodes_becomes_a_failed_result(self) -> None:
        preprocessor = FakeImagePreprocessor()
        preprocessor.prepare = _raises(RuntimeError("boom"))  # type: ignore[method-assign]
        result = await run(build(preprocessor=preprocessor))
        assert result.status is OcrSessionStatus.FAILED
        assert result.error_code == "UNEXPECTED_ERROR"
        assert result.diagnostics[0].code == "UNEXPECTED"

    async def test_out_of_memory_is_reported_not_propagated(self) -> None:
        preprocessor = FakeImagePreprocessor()
        preprocessor.prepare = _raises(MemoryError())  # type: ignore[method-assign]
        result = await run(build(preprocessor=preprocessor))
        assert result.status is OcrSessionStatus.FAILED
        assert result.error_code == "OUT_OF_MEMORY"

    async def test_a_qr_decoder_that_raises_does_not_lose_the_other_channels(self) -> None:
        """§7.3 forbids it, so this is about surviving a buggy adapter."""
        pipeline = build(mrz=mrz_result())
        pipeline._qr_decoder.decode = _raises(RuntimeError("zxing fell over"))  # type: ignore[method-assign, union-attr]
        result = await run(pipeline)
        assert result.status is not OcrSessionStatus.FAILED
        assert result.value(FieldKey.ID_NUMBER) == ID_NUMBER

    async def test_a_progress_callback_that_raises_does_not_lose_the_extraction(self) -> None:
        def hostile(percent: int, message: str) -> None:
            raise RuntimeError("the progress writer died")

        result = await run(build(qr=qr_result()), progress=hostile)
        assert result.status is not OcrSessionStatus.FAILED
        assert result.value(FieldKey.FULL_NAME) == FULL_NAME

    async def test_an_empty_document_type_list_is_reported_not_raised(self) -> None:
        result = await build().execute(b"a", b"b", [])
        assert result.status is OcrSessionStatus.FAILED
        assert result.error_code == "NO_DOCUMENT_TYPE"


class TestProgress:
    """⭐ "`progress` được gọi ít nhất một lần mỗi chặng" (§12.3)."""

    async def test_every_stage_reports_once_on_the_happy_path(self) -> None:
        seen: list[tuple[int, str]] = []
        await run(
            build(qr=qr_result(), mrz=mrz_result()),
            progress=lambda p, m: seen.append((p, m)),
        )
        assert len(seen) == 9, seen

    async def test_percentages_never_go_backwards(self) -> None:
        seen: list[tuple[int, str]] = []
        await run(build(qr=qr_result(), mrz=mrz_result()), progress=lambda p, m: seen.append((p, m)))
        percents = [percent for percent, _ in seen]
        assert percents == sorted(percents)

    async def test_messages_are_vietnamese_and_non_empty(self) -> None:
        seen: list[tuple[int, str]] = []
        await run(build(), progress=lambda p, m: seen.append((p, m)))
        assert all(message.strip() for _, message in seen)
        assert any("Đang" in message for _, message in seen)


class TestSideClassification:
    """S4's three verdicts map onto three different statuses (§7.7)."""

    async def test_auto_swap_is_recorded_and_the_sides_follow_the_verdict(self) -> None:
        swapped = SideClassification(
            front_index=1,
            back_index=0,
            confidence_a=0.4,
            confidence_b=0.95,
            swapped=True,
            verdict=SideVerdict.RESOLVED,
        )
        result = await run(build(classification=swapped, qr=qr_result()))
        assert result.auto_swapped is True
        assert result.detected_sides == {0: CardSide.BACK, 1: CardSide.FRONT}
        assert any(d.code == "SIDES_AUTO_SWAPPED" for d in result.diagnostics)

    async def test_duplicate_side_needs_a_reupload_and_is_not_a_failure(self) -> None:
        duplicate = SideClassification(
            front_index=0,
            back_index=1,
            confidence_a=0.9,
            confidence_b=0.9,
            swapped=False,
            verdict=SideVerdict.DUPLICATE_SIDE,
        )
        result = await run(build(classification=duplicate))
        assert result.status is OcrSessionStatus.NEEDS_REUPLOAD
        assert result.error_code is None
        assert result.detected_sides == {0: CardSide.FRONT, 1: CardSide.FRONT}

    async def test_ambiguous_sides_ask_the_user_rather_than_guessing(self) -> None:
        ambiguous = SideClassification(
            front_index=0,
            back_index=1,
            confidence_a=0.2,
            confidence_b=0.2,
            swapped=False,
            verdict=SideVerdict.AMBIGUOUS,
        )
        result = await run(build(classification=ambiguous))
        assert result.status is OcrSessionStatus.NEEDS_MANUAL_ASSIGN
        assert result.error_code is None
        assert set(result.fields) == set(FieldKey)

    async def test_an_unresolved_verdict_stops_before_the_recognizer_runs(self) -> None:
        """The expensive stage must not be paid for a card that needs reuploading."""
        engine = FakeOcrEngine([region("anything")])
        pipeline = build(
            engine=engine,
            classification=SideClassification(
                front_index=0, back_index=1, confidence_a=0.2, confidence_b=0.2,
                swapped=False, verdict=SideVerdict.AMBIGUOUS,
            ),
        )
        result = await run(pipeline)
        assert result.channel_summary.text_passes == 0
        assert result.status is OcrSessionStatus.NEEDS_MANUAL_ASSIGN


class TestDegradation:
    """§7.7: a dead channel is a degradation, never the end of the run (P-08)."""

    async def test_a_dead_engine_still_completes_using_qr(self) -> None:
        engine = FakeOcrEngine()
        engine.recognize = _raises(OcrEngineUnavailableError("model chưa nạp"))  # type: ignore[method-assign]
        result = await run(build(engine=engine, qr=qr_result()))
        assert result.status is not OcrSessionStatus.FAILED
        assert result.value(FieldKey.FULL_NAME) == FULL_NAME
        assert any(d.code == "OCR_ENGINE_UNAVAILABLE" for d in result.diagnostics)

    async def test_an_engine_timeout_on_one_photo_is_a_diagnostic_not_a_failure(self) -> None:
        engine = FakeOcrEngine()
        engine.recognize = _raises(OcrTimeoutError("quá 30s"))  # type: ignore[method-assign]
        result = await run(build(engine=engine, mrz=mrz_result()))
        assert result.status is not OcrSessionStatus.FAILED
        assert result.value(FieldKey.EXPIRY_DATE) == EXPIRY_DATE

    async def test_a_failed_mrz_read_leaves_the_qr_fields_standing(self) -> None:
        pipeline = build(qr=qr_result())
        pipeline._mrz_reader.read = _raises(OcrTimeoutError("MRZ quá lâu"))  # type: ignore[method-assign, union-attr]
        result = await run(pipeline)
        assert result.value(FieldKey.ID_NUMBER) == ID_NUMBER
        assert any(d.stage == "S6" for d in result.diagnostics)

    async def test_a_bad_mrz_checksum_is_reported_but_still_used(self) -> None:
        result = await run(build(mrz=mrz_result(checksum_valid=False, confidence=0.50)))
        assert any(d.code == "MRZ_CHECKSUM_FAILED" for d in result.diagnostics)
        assert result.value(FieldKey.ID_NUMBER) == ID_NUMBER

    async def test_an_unrecognized_qr_layout_contributes_nothing_and_says_so(self) -> None:
        """⭐ §7.3's designed-in escape hatch: degrade to no fields, not garbage."""
        result = await run(build(qr=qr_result(layout_recognized=False, fields={})))
        assert any(d.code == "QR_LAYOUT_UNRECOGNIZED" for d in result.diagnostics)
        assert result.value(FieldKey.FULL_NAME) is None

    async def test_a_document_type_without_ocr_support_skips_the_text_channel(self) -> None:
        engine = FakeOcrEngine([region("anything")])
        pipeline = build(engine=engine, qr=qr_result())
        result = await pipeline.execute(
            b"front", b"back", [doc_type(is_ocr_supported=False)]
        )
        assert result.channel_summary.text_passes == 0
        assert result.value(FieldKey.ID_NUMBER) == ID_NUMBER


class TestLeverOneWholeCardPass:
    """⭐ At most one recognition pass per photo — §7.4.6 finding 20."""

    async def test_a_photo_is_never_recognized_twice(self) -> None:
        engine = _CountingEngine([region("CĂN CƯỚC CÔNG DÂN", y=0.1)])
        await build(engine=engine).execute(
            b"front", b"back", [CCCD_2021, CAN_CUOC_2024]
        )
        assert engine.recognize_calls <= 2

    async def test_generation_selection_uses_the_regions_already_read(self) -> None:
        engine = _CountingEngine([region("Số định danh cá nhân", y=0.1)])
        selector = FakeDocumentTypeSelector(CAN_CUOC_2024)
        result = await build(engine=engine, selector=selector).execute(
            b"front", b"back", [CCCD_2021, CAN_CUOC_2024]
        )
        assert selector.calls, "the selector was never consulted"
        assert engine.recognize_calls <= 2
        assert result.card_generation == "CAN_CUOC_2024"
        assert any(d.code == "DOCUMENT_TYPE_RESELECTED" for d in result.diagnostics)

    async def test_a_single_document_type_skips_selection_entirely(self) -> None:
        selector = FakeDocumentTypeSelector(CAN_CUOC_2024)
        result = await run(build(selector=selector))
        assert selector.calls == []
        assert result.card_generation == "CCCD_CHIP"

    async def test_extraction_uses_the_type_the_selector_chose(self) -> None:
        extractor = FakeFieldExtractor()
        selector = FakeDocumentTypeSelector(CAN_CUOC_2024)
        await build(extractor=extractor, selector=selector).execute(
            b"front", b"back", [CCCD_2021, CAN_CUOC_2024]
        )
        assert {code for _, code in extractor.calls} == {"CAN_CUOC_2024"}


class TestLeverTwoSkippingAPass:
    """⭐ Do not recognize a photo that has nothing left to contribute."""

    async def test_the_front_is_skipped_when_qr_and_mrz_covered_everything_on_it(self) -> None:
        result = await run(build(qr=qr_result(), mrz=mrz_result()))
        assert result.channel_summary.text_passes == 1
        skipped = [d for d in result.diagnostics if d.code == "TEXT_PASS_SKIPPED"]
        assert [d.side for d in skipped] == [CardSide.FRONT]

    async def test_the_back_is_never_skipped_because_issue_place_has_no_exact_channel(
        self,
    ) -> None:
        result = await run(build(qr=qr_result(), mrz=mrz_result()))
        assert CardSide.BACK not in {
            d.side for d in result.diagnostics if d.code == "TEXT_PASS_SKIPPED"
        }

    async def test_nothing_is_skipped_when_no_exact_channel_worked(self) -> None:
        result = await run(build())
        assert result.channel_summary.text_passes == 2
        assert not [d for d in result.diagnostics if d.code == "TEXT_PASS_SKIPPED"]

    async def test_force_full_ocr_overrides_the_skip(self) -> None:
        result = await run(build(qr=qr_result(), mrz=mrz_result()), force_full_ocr=True)
        assert result.channel_summary.text_passes == 2
        assert not [d for d in result.diagnostics if d.code == "TEXT_PASS_SKIPPED"]

    async def test_a_weak_exact_reading_still_earns_the_pass(self) -> None:
        """Below `CORROBORATION_FLOOR` a field is worth a second opinion."""
        weak = mrz_result(confidence=0.50, checksum_valid=False)
        result = await run(build(qr=qr_result(layout_recognized=False, fields={}), mrz=weak))
        assert result.channel_summary.text_passes == 2


class TestSidesWorthReading:
    """The lever's decision function, isolated from the pipeline."""

    def test_zone_map_side_labels_drive_the_field_map(self) -> None:
        assert _fields_printed_on([CCCD_2021], CardSide.FRONT) == frozenset(
            {
                FieldKey.ID_NUMBER,
                FieldKey.FULL_NAME,
                FieldKey.DATE_OF_BIRTH,
                FieldKey.EXPIRY_DATE,
            }
        )

    def test_the_mrz_zone_is_not_mistaken_for_a_business_field(self) -> None:
        every = _fields_printed_on([CCCD_2021], CardSide.FRONT) | _fields_printed_on(
            [CCCD_2021], CardSide.BACK
        )
        assert every == set(FieldKey)

    def test_the_field_map_is_the_union_over_every_candidate_type(self) -> None:
        """⚠️ 2021 prints the expiry on the front, 2024 on the back — so with
        both in play, neither side may be written off on that field alone."""
        both = [CCCD_2021, CAN_CUOC_2024]
        assert FieldKey.EXPIRY_DATE in _fields_printed_on(both, CardSide.FRONT)
        assert FieldKey.EXPIRY_DATE in _fields_printed_on(both, CardSide.BACK)

    def test_everything_read_confidently_means_nothing_is_worth_reading(self) -> None:
        full = {
            key: [Candidate(value="x", source=FieldSource.QR, confidence=1.0)]
            for key in FieldKey
        }
        assert _sides_worth_reading([CCCD_2021], full) == frozenset()

    def test_one_weak_field_revives_its_side_only(self) -> None:
        candidates = {
            key: [Candidate(value="x", source=FieldSource.QR, confidence=1.0)]
            for key in FieldKey
        }
        candidates[FieldKey.ISSUE_PLACE] = [
            Candidate(value=BO_CONG_AN, source=FieldSource.OCR, confidence=0.60)
        ]
        assert _sides_worth_reading([CCCD_2021], candidates) == frozenset({CardSide.BACK})

    def test_the_floor_is_the_review_threshold_not_zero(self) -> None:
        """A field the user must check anyway is worth corroborating."""
        just_below = {
            key: [Candidate(value="x", source=FieldSource.QR, confidence=CORROBORATION_FLOOR - 0.01)]
            for key in FieldKey
        }
        assert _sides_worth_reading([CCCD_2021], just_below) == frozenset(
            {CardSide.FRONT, CardSide.BACK}
        )


class TestFusionAndProvenance:
    """S9→S10, and the trace §5.3.4 renders around each value."""

    async def test_qr_beats_ocr_for_the_same_field(self) -> None:
        extractor = FakeFieldExtractor({FieldKey.FULL_NAME: raw("NGUYEN VAN AN")})
        result = await run(build(qr=qr_result(), extractor=extractor, mrz=mrz_result()))
        assert result.fields[FieldKey.FULL_NAME].source is FieldSource.QR
        assert result.value(FieldKey.FULL_NAME) == FULL_NAME

    async def test_losing_candidates_are_kept_with_whether_they_agreed(self) -> None:
        extractor = FakeFieldExtractor(
            by_side={CardSide.BACK: {FieldKey.ID_NUMBER: raw(ID_NUMBER)}}
        )
        result = await run(build(qr=qr_result(), extractor=extractor))
        traces = result.fields[FieldKey.ID_NUMBER].candidates
        assert {t.source for t in traces} == {FieldSource.QR, FieldSource.OCR}
        assert all(t.agrees for t in traces)

    async def test_the_raw_reading_survives_even_when_normalization_rejected_it(self) -> None:
        """⭐ The field the user must retype is where seeing the raw text is worth most."""
        extractor = FakeFieldExtractor({FieldKey.DATE_OF_BIRTH: raw("khong doc duoc")})
        result = await run(build(extractor=extractor))
        assert result.value(FieldKey.DATE_OF_BIRTH) is None
        assert result.fields[FieldKey.DATE_OF_BIRTH].raw_value == "khong doc duoc"

    async def test_the_bbox_travels_with_the_field_for_the_image_inspector(self) -> None:
        extractor = FakeFieldExtractor({FieldKey.FULL_NAME: raw("NGUYEN VAN AN")})
        result = await run(build(extractor=extractor))
        assert result.fields[FieldKey.FULL_NAME].bbox is not None

    async def test_dates_arrive_normalized_to_iso_from_every_channel(self) -> None:
        """⭐ Why S9 exists at all: QR says `14051999`, the extractor says
        `14/05/1999`, and fusion compares with `==`."""
        extractor = FakeFieldExtractor({FieldKey.DATE_OF_BIRTH: raw("14/05/1999")})
        result = await run(build(qr=qr_result(), extractor=extractor, mrz=mrz_result()))
        assert result.value(FieldKey.DATE_OF_BIRTH) == BIRTH_DATE
        assert result.fields[FieldKey.DATE_OF_BIRTH].fused.agreement is True

    async def test_overall_confidence_is_a_real_number_in_range(self) -> None:
        result = await run(build(qr=qr_result(), mrz=mrz_result()))
        assert 0.0 <= result.overall_confidence <= 1.0
        assert result.overall_confidence > 0.0


class TestChannelSummary:
    async def test_it_reports_what_each_channel_actually_did(self) -> None:
        result = await run(build(qr=qr_result(), mrz=mrz_result()))
        summary = result.channel_summary
        assert summary.qr_available and summary.qr_layout_recognized
        assert summary.mrz_available and summary.mrz_checksum_valid is True
        assert summary.ocr_available
        assert summary.any_channel_worked

    async def test_a_card_with_no_channels_says_so(self) -> None:
        result = await run(build(engine=NullOcrEngine()))
        assert not result.channel_summary.any_channel_worked


class TestValidation:
    """S11 ran, and its verdict is separate from the run's own status."""

    async def test_all_23_ocr_rules_ran(self) -> None:
        result = await run(build(engine=NullOcrEngine()))
        codes = {issue.code for issue in result.validation_report.issues}
        assert codes, "an empty card must raise something"
        assert all(code.startswith("V-OCR-") for code in codes)

    async def test_a_card_with_errors_still_counts_as_a_completed_extraction(self) -> None:
        """⭐ There is no COMPLETED_WITH_ERRORS: the run worked, the card did not."""
        result = await run(build(engine=NullOcrEngine()))
        assert result.validation_report.is_valid is False
        assert result.status is OcrSessionStatus.COMPLETED_WITH_WARNINGS
        assert result.error_code is None

    async def test_today_comes_from_the_clock_port_not_the_wall_clock(self) -> None:
        pipeline = ExtractionPipeline(
            preprocessor=FakeImagePreprocessor(),
            side_classifier=FakeCardSideClassifier(),
            qr_decoder=FakeQrDecoder(qr_result()),
            mrz_reader=FakeMrzReader(mrz_result()),
            engine=FakeOcrEngine(),
            extractor=FakeFieldExtractor(),
            doc_type_selector=FakeDocumentTypeSelector(),
            normalizer=FieldNormalizer(IssuePlaceNormalizer(FakeAliasRepository())),
            clock=FrozenClock(datetime(2050, 1, 1, tzinfo=UTC)),
        )
        result = await pipeline.execute(b"a", b"b", [CCCD_2021])
        # The card expires in 2044, so a 2050 "today" must see it as expired.
        assert any(
            issue.code == "V-OCR-013" for issue in result.validation_report.issues
        ), result.validation_report.codes()


class TestDtoInvariants:
    def test_a_result_missing_a_field_key_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="missing field keys"):
            ExtractionResult(status=OcrSessionStatus.COMPLETED, fields={})

    def test_a_lifecycle_status_the_pipeline_cannot_produce_is_rejected(self) -> None:
        from cocas.application.dto.extraction import empty_fields

        with pytest.raises(ValueError, match="not a status the pipeline can produce"):
            ExtractionResult(status=OcrSessionStatus.QUEUED, fields=empty_fields())

    def test_an_error_code_without_a_failure_is_rejected(self) -> None:
        from cocas.application.dto.extraction import empty_fields

        with pytest.raises(ValueError, match="error_code"):
            ExtractionResult(
                status=OcrSessionStatus.COMPLETED, fields=empty_fields(), error_code="OOPS"
            )


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _raises(exc: BaseException):  # type: ignore[no-untyped-def]
    def _boom(*args: object, **kwargs: object) -> None:
        raise exc

    return _boom


class _CountingEngine(FakeOcrEngine):
    """Counts whole-card passes — the number the p95 budget lives on."""

    def __init__(self, regions: list[TextRegion] | None = None) -> None:
        super().__init__(regions)
        self.recognize_calls = 0

    def recognize(self, image, options):  # type: ignore[no-untyped-def]
        self.recognize_calls += 1
        return super().recognize(image, options)


def test_date_helpers_are_consistent() -> None:
    """Guards the fixtures themselves: a wrong constant here fakes a pass."""
    assert date.fromisoformat(BIRTH_DATE) == date(1999, 5, 14)
    assert date.fromisoformat(ISSUE_DATE) == date(2021, 8, 20)
    assert date.fromisoformat(EXPIRY_DATE) == date(2044, 5, 14)
