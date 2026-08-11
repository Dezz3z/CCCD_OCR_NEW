"""`ExtractionPipeline` — the 9 stages S3→S11 in one call (§12.3, §03, §7.7).

⭐ **This is the only place the three OCR channels are combined**, and P-04
lives here: extraction is never "just OCR". QR, MRZ and the text recognizer
each get a turn; `FieldFusionService` decides between them.

⭐ **It never raises.** §12.3 makes that an invariant, not a style preference:
the pipeline runs inside a `job` row picked up by a background worker, and an
exception escaping here kills the worker for every queued card, not just this
one. Every failure becomes a `status` and an `error_code` instead — see §7.7
for which stage failures are fatal (`FAILED`), which need the user
(`NEEDS_REUPLOAD` / `NEEDS_MANUAL_ASSIGN`), and which are simply degradations
that must not stop the run.

## The latency levers

§7.4.6 measured the whole chain at 7.7 s mean per *image* against a 9 s budget
per *pair*, and found the cost is almost entirely whole-card recognition. So:

1. ⭐ **At most one whole-card pass per image**, never two. The card generation
   is inferred from the regions that pass already produced
   (`IDocumentTypeSelector`), not from a pass of its own. Reading the card
   twice cost 28–45 s per image on a 4 GB machine — five to seven times the
   single pass, not double it, because the second pass runs with the first
   one's arrays still resident.
2. ⭐ **A pass is skipped entirely when that side has nothing left to give.**
   QR yields 4 fields and MRZ 3; on a card where both channels worked, one of
   the two photos is left contributing nothing, and recognizing it is pure
   cost. `_sides_worth_reading` works this out from `zone_map`, so it stays
   right for a document type nobody has written yet (NFR-10).
3. **The two photos are prepared concurrently.** Only the cheap stages —
   decode, preprocess, QR — actually overlap: everything that touches the
   recognizer is serialized behind `_engine_lock`, because two PaddleOCR passes
   at once on a 4 GB machine produce `Insufficient memory` from inside OpenCV
   rather than an honest failure.

⚠️ Lever 3 is worth the least of the three and is not why the budget is met.
It is here because the budget is stated per *pair* while every measurement to
date is per *image*, and overlapping the non-recognizer work is the only part
of that gap the pipeline itself can close.

⚠️ Every port call goes through `asyncio.to_thread`, and the argument
evaluation matters: `PreprocessedImageSet` builds its variants **on attribute
access** (§12.4), so `to_thread(engine.recognize, image_set.v3, …)` would build
`v3` on the event loop and hand the thread a finished array. The lazy access
has to happen *inside* the worker — hence the small `_sync` methods below.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from cocas.application.dto.extraction import (
    EMPTY_FUSED,
    CandidateTrace,
    ChannelSummary,
    Diagnostic,
    ExtractedField,
    ExtractionResult,
    ProgressCallback,
    empty_fields,
    noop_progress,
)
from cocas.domain.enums.card_side import CardSide
from cocas.domain.enums.field_key import FieldKey
from cocas.domain.enums.field_source import FieldSource
from cocas.domain.enums.ocr_session_status import OcrSessionStatus
from cocas.domain.exceptions import OcrProcessingError
from cocas.domain.ports.ocr import (
    DocumentTypeSpec,
    ICardSideClassifier,
    IDocumentTypeSelector,
    IFieldExtractor,
    IImagePreprocessor,
    IMrzReader,
    IOcrEngine,
    IQrDecoder,
    MrzExtractionResult,
    OcrOptions,
    PreprocessedImageSet,
    PreprocessProfile,
    QrExtractionResult,
    RawFieldValue,
    SideClassification,
    SideVerdict,
    TextRegion,
)
from cocas.domain.ports.system import IClock
from cocas.domain.services.confidence_calculator import ConfidenceCalculator
from cocas.domain.services.field_fusion_service import (
    Candidate,
    FieldFusionService,
    FusedField,
    FusionContext,
)
from cocas.domain.services.field_normalizer import FieldNormalizer, NormalizedValue
from cocas.domain.validation.engine import ValidationEngine
from cocas.domain.validation.ocr_rules import OcrValidationTarget
from cocas.domain.validation.rule import RuleContext, RuleSetKey

# (percent, Vietnamese message) announced as each stage begins. The percentages
# are deliberately uneven: S7 is most of the wall clock, so a bar that moved in
# equal steps would sit at 55% for four fifths of the run (§5.3.5).
_STAGE_PROGRESS: Mapping[str, tuple[int, str]] = {
    "S3": (5, "Đang xử lý ảnh…"),
    "S5": (18, "Đang đọc mã QR…"),
    "S4": (28, "Đang xác định mặt trước / mặt sau…"),
    "S6": (36, "Đang đọc vùng MRZ mặt sau…"),
    "S7": (45, "Đang nhận dạng chữ trên thẻ…"),
    "S8": (80, "Đang trích xuất thông tin…"),
    "S9": (88, "Đang chuẩn hoá dữ liệu…"),
    "S10": (94, "Đang đối chiếu ba nguồn…"),
    "S11": (98, "Đang kiểm tra tính hợp lệ…"),
}

# ⭐ Below this, a field is worth another channel's effort. Deliberately the
# same number fusion uses to flag a field for human review: a value the user
# will have to check anyway is a value the text channel should still try to
# corroborate.
CORROBORATION_FLOOR = 0.85

_BOTH_SIDES = frozenset({CardSide.FRONT, CardSide.BACK})


@dataclass(slots=True)
class _ImageRead:
    """Everything one uploaded photo produced, before the two are merged."""

    index: int
    image_set: PreprocessedImageSet | None = None
    qr: QrExtractionResult = field(default_factory=lambda: QrExtractionResult(available=False))
    mrz: MrzExtractionResult = field(default_factory=lambda: MrzExtractionResult(available=False))
    regions: list[TextRegion] = field(default_factory=list)
    raw: dict[FieldKey, RawFieldValue] = field(default_factory=dict)
    side: CardSide = CardSide.FRONT
    text_pass_ran: bool = False
    decode_error: str | None = None


class ExtractionPipeline:
    """Application service — see the module docstring.

    Every collaborator is a Port or a Domain Service, so the whole pipeline runs
    against `tests/fixtures/fake_ports.py` with no images, no models and no
    database (§12.2's acceptance criterion).
    """

    def __init__(
        self,
        preprocessor: IImagePreprocessor,
        side_classifier: ICardSideClassifier,
        qr_decoder: IQrDecoder,
        mrz_reader: IMrzReader,
        engine: IOcrEngine,
        extractor: IFieldExtractor,
        doc_type_selector: IDocumentTypeSelector,
        normalizer: FieldNormalizer,
        clock: IClock,
        fusion: FieldFusionService | None = None,
        confidence: ConfidenceCalculator | None = None,
        validation: ValidationEngine | None = None,
    ) -> None:
        self._preprocessor = preprocessor
        self._side_classifier = side_classifier
        self._qr_decoder = qr_decoder
        self._mrz_reader = mrz_reader
        self._engine = engine
        self._extractor = extractor
        self._doc_type_selector = doc_type_selector
        self._normalizer = normalizer
        self._clock = clock
        self._fusion = fusion or FieldFusionService()
        self._confidence = confidence or ConfidenceCalculator()
        self._validation = validation or ValidationEngine()
        # ⭐ One recognizer, one caller at a time. See lever 3 in the module
        # docstring — this is a memory guard, not a correctness guard.
        self._engine_lock = asyncio.Lock()

    async def execute(
        self,
        front_image: bytes,
        back_image: bytes,
        doc_types: Sequence[DocumentTypeSpec],
        progress: ProgressCallback = noop_progress,
        *,
        profile: PreprocessProfile | None = None,
        known_province_codes: frozenset[str] = frozenset(),
        force_full_ocr: bool = False,
    ) -> ExtractionResult:
        """Run S3→S11 over one pair of photos. **Never raises** (§12.3).

        Args:
            front_image: bytes of the photo the caller believes is the front.
            back_image: the other one. ⭐ Both are "believed" — S4 decides, and
                swapping them is a normal outcome, not an error.
            doc_types: the active `document_type` rows this card might be, most
                likely first. A single-element sequence pins the type and
                skips selection entirely, which is §12.3's original signature.
            progress: called at least once per stage with `(percent, message_vi)`.
            profile: preprocessing tuning; the default profile when None.
            known_province_codes: the 63 codes, for fusion rule 6 and V-OCR-021.
                Empty disables the province cross-check rather than failing it.
            force_full_ocr: recognize both photos even where lever 2 would skip
                one (§5.3.3 `options.force_full_ocr`) — the escape hatch for a
                user who thinks the QR lied.

        Returns:
            An `ExtractionResult` whose `status` says what happened. Callers
            branch on that; there is nothing to catch.
        """
        started = time.perf_counter()
        if not doc_types:
            return _failed("NO_DOCUMENT_TYPE", started, ())
        try:
            return await self._run(
                front_image,
                back_image,
                doc_types,
                progress,
                profile or PreprocessProfile(),
                known_province_codes,
                force_full_ocr,
                started,
            )
        except MemoryError:
            # §7.7 classifies this as fatal, and it is the failure most likely
            # to arrive from somewhere nobody instrumented. Caught before
            # `Exception` because it is one.
            return _failed("OUT_OF_MEMORY", started, ())
        except OcrProcessingError as exc:
            # Stage handlers catch their own; this is the net under the rest.
            return _failed(exc.code, started, ())
        except Exception as exc:
            return _failed(
                "UNEXPECTED_ERROR",
                started,
                (_diag("pipeline", "UNEXPECTED", type(exc).__name__),),
            )

    # ------------------------------------------------------------------
    # The run itself
    # ------------------------------------------------------------------

    async def _run(
        self,
        front_image: bytes,
        back_image: bytes,
        doc_types: Sequence[DocumentTypeSpec],
        progress: ProgressCallback,
        profile: PreprocessProfile,
        known_province_codes: frozenset[str],
        force_full_ocr: bool,
        started: float,
    ) -> ExtractionResult:
        declared = doc_types[0]
        diagnostics: list[Diagnostic] = []

        # -- S3 — preprocess both photos, concurrently -------------------
        _announce(progress, "S3")
        reads = list(
            await asyncio.gather(
                self._preprocess(0, front_image, profile),
                self._preprocess(1, back_image, profile),
            )
        )
        fatal = next((r for r in reads if r.decode_error is not None), None)
        if fatal is not None:
            return _failed(
                fatal.decode_error or "IMAGE_DECODE_ERROR",
                started,
                (_diag("S3", "IMAGE_UNREADABLE", f"Ảnh thứ {fatal.index + 1} không đọc được."),),
            )

        # -- S5 — QR on both, concurrently, still no recognizer ----------
        _announce(progress, "S5")
        await asyncio.gather(*(self._decode_qr(read) for read in reads))
        for read in reads:
            if read.qr.available and not read.qr.layout_recognized:
                diagnostics.append(
                    _diag("S5", "QR_LAYOUT_UNRECOGNIZED", "Mã QR đọc được nhưng bố cục lạ.")
                )

        # -- S4 ----------------------------------------------------------
        _announce(progress, "S4")
        classification = await self._classify(reads, declared)
        blocked = _side_failure(classification, reads, started, diagnostics)
        if blocked is not None:
            return blocked
        reads[classification.front_index].side = CardSide.FRONT
        reads[classification.back_index].side = CardSide.BACK
        if classification.swapped:
            diagnostics.append(
                _diag("S4", "SIDES_AUTO_SWAPPED", "Đã tự động hoán đổi ảnh mặt trước và mặt sau.")
            )

        # -- S6 ----------------------------------------------------------
        _announce(progress, "S6")
        await self._read_mrz(reads, declared, diagnostics)

        # ⭐ QR and MRZ are normalized here, *before* S7, so lever 2 can ask
        # what is still missing. Doing it afterwards would mean recognizing a
        # card to fill fields that were already full.
        candidates: dict[FieldKey, list[Candidate]] = {key: [] for key in FieldKey}
        for read in reads:
            await self._collect_exact(read, candidates)

        # -- S7 ----------------------------------------------------------
        _announce(progress, "S7")
        resolved = await self._recognize_text(
            reads, doc_types, declared, candidates, force_full_ocr, diagnostics
        )

        # -- S8 ----------------------------------------------------------
        _announce(progress, "S8")
        for read in reads:
            if read.regions:
                read.raw = await asyncio.to_thread(self._extract_sync, read, resolved)

        # -- S9 ----------------------------------------------------------
        _announce(progress, "S9")
        provenance: dict[FieldKey, RawFieldValue] = {}
        tiers: dict[FieldKey, int] = {}
        for read in reads:
            await self._collect_text(read, candidates, provenance, tiers)

        # -- S10 ---------------------------------------------------------
        _announce(progress, "S10")
        fused = self._fusion.fuse(
            candidates, FusionContext(known_province_codes=known_province_codes)
        )
        overall = self._confidence.overall(fused)

        # -- S11 ---------------------------------------------------------
        # `has_*_image` are both true by construction: a run that reaches S11
        # got a RESOLVED verdict at S4, and that verdict names one photo per
        # side. V-OCR-001/002 protect the paths that return before here.
        _announce(progress, "S11")
        report = self._validation.validate(
            OcrValidationTarget(
                fields=fused, has_front_image=True, has_back_image=True, duplicate_side=False
            ),
            RuleSetKey.OCR_RESULT,
            RuleContext(today=self._clock.today(), known_province_codes=known_province_codes),
        )

        return ExtractionResult(
            status=_status_for(report.issues != ()),
            fields=_assemble(candidates, fused, provenance, tiers),
            channel_summary=_summarize(reads),
            validation_report=report,
            diagnostics=tuple(diagnostics),
            overall_confidence=overall,
            auto_swapped=classification.swapped,
            duration_ms=_elapsed_ms(started),
            card_generation=resolved.code,
            detected_sides={read.index: read.side for read in reads},
        )

    # ------------------------------------------------------------------
    # S3, S5 — per photo, no recognizer involved
    # ------------------------------------------------------------------

    async def _preprocess(
        self, index: int, image_bytes: bytes, profile: PreprocessProfile
    ) -> _ImageRead:
        """§03 S3. A decode failure is recorded, not raised — so the caller
        learns *which* photo is unreadable instead of only that one was."""
        read = _ImageRead(index=index)
        try:
            read.image_set = await asyncio.to_thread(
                self._preprocessor.prepare, image_bytes, None, profile
            )
        except OcrProcessingError as exc:
            read.decode_error = exc.code
        return read

    async def _decode_qr(self, read: _ImageRead) -> None:
        """§03 S5. ⭐ §7.3 forbids `IQrDecoder` from raising; if an adapter does
        it anyway, that is a bug in the adapter and not a reason to lose the
        other two channels."""
        if read.image_set is None:
            return
        try:
            read.qr = await asyncio.to_thread(self._qr_decoder.decode, read.image_set)
        except Exception:
            read.qr = QrExtractionResult(available=False)

    # ------------------------------------------------------------------
    # S4 — side classification
    # ------------------------------------------------------------------

    async def _classify(
        self, reads: Sequence[_ImageRead], doc_type: DocumentTypeSpec
    ) -> SideClassification:
        """§03 S4. Reads the title band, so it takes the recognizer lock."""
        first, second = reads[0].image_set, reads[1].image_set
        if first is None or second is None:  # unreachable — S3 already returned
            return _UNRESOLVED
        async with self._engine_lock:
            return await asyncio.to_thread(
                self._side_classifier.classify, first, second, doc_type
            )

    # ------------------------------------------------------------------
    # S6 — MRZ
    # ------------------------------------------------------------------

    async def _read_mrz(
        self,
        reads: Sequence[_ImageRead],
        doc_type: DocumentTypeSpec,
        diagnostics: list[Diagnostic],
    ) -> None:
        """§03 S6 — the back only. Reads regions, so it takes the lock."""
        if not doc_type.has_mrz:
            return
        back = next((r for r in reads if r.side is CardSide.BACK), None)
        if back is None or back.image_set is None:
            return
        try:
            async with self._engine_lock:
                back.mrz = await asyncio.to_thread(
                    self._mrz_reader.read, back.image_set, doc_type
                )
        except OcrProcessingError as exc:
            # §7.7: "Kênh MRZ thất bại — bình thường". The expiry date may end
            # up yellow; nothing else changes.
            diagnostics.append(_diag("S6", exc.code, "Không đọc được vùng MRZ.", CardSide.BACK))
            return
        if back.mrz.available and back.mrz.checksum_valid is False:
            diagnostics.append(
                _diag(
                    "S6",
                    "MRZ_CHECKSUM_FAILED",
                    "Vùng MRZ đọc được nhưng sai số kiểm.",
                    CardSide.BACK,
                )
            )

    # ------------------------------------------------------------------
    # S7 — the text channel, and the two levers that govern it
    # ------------------------------------------------------------------

    async def _recognize_text(
        self,
        reads: Sequence[_ImageRead],
        doc_types: Sequence[DocumentTypeSpec],
        declared: DocumentTypeSpec,
        candidates: Mapping[FieldKey, list[Candidate]],
        force_full_ocr: bool,
        diagnostics: list[Diagnostic],
    ) -> DocumentTypeSpec:
        """Recognize the photos worth recognizing (§03 S7), then settle the type.

        Returns the document type the run uses for extraction — the declared
        one unless the recognized text says otherwise.
        """
        if not declared.is_ocr_supported:
            return declared

        wanted = _BOTH_SIDES if force_full_ocr else _sides_worth_reading(doc_types, candidates)
        for read in reads:
            if read.side not in wanted:
                diagnostics.append(
                    _diag(
                        "S7",
                        "TEXT_PASS_SKIPPED",
                        "Bỏ qua nhận dạng chữ — QR/MRZ đã cung cấp đủ thông tin của mặt này.",
                        read.side,
                    )
                )
                continue
            await self._recognize_one(read, diagnostics)

        # ⭐ Generation decided from regions already paid for — never a new pass.
        every_region = [region for read in reads for region in read.regions]
        resolved = declared
        if len(doc_types) > 1 and every_region:
            picked = self._doc_type_selector.select(every_region, doc_types)
            if picked is not None:
                resolved = picked
        if resolved.code != declared.code:
            diagnostics.append(
                _diag(
                    "S7",
                    "DOCUMENT_TYPE_RESELECTED",
                    f"Nhận dạng thẻ thuộc thế hệ '{resolved.name}'.",
                )
            )
        return resolved

    async def _recognize_one(self, read: _ImageRead, diagnostics: list[Diagnostic]) -> None:
        """⭐ **One** whole-card pass, on the `v3` variant §7.4.1 assigns to text."""
        if read.image_set is None:
            return
        try:
            async with self._engine_lock:
                read.regions = await asyncio.to_thread(self._recognize_sync, read.image_set)
            read.text_pass_ran = True
        except OcrProcessingError as exc:
            # §7.7: the engine dying is a degradation, never the end of the run.
            # A card whose QR was read is still a usable card (P-08).
            diagnostics.append(
                _diag("S7", exc.code, "Không nhận dạng được chữ trên ảnh này.", read.side)
            )

    def _recognize_sync(self, image_set: PreprocessedImageSet) -> list[TextRegion]:
        """⭐ `.v3` is built here, inside the worker thread — see the module
        docstring's note on lazy variants and argument evaluation."""
        return self._engine.recognize(image_set.v3, OcrOptions())

    def _extract_sync(
        self, read: _ImageRead, doc_type: DocumentTypeSpec
    ) -> dict[FieldKey, RawFieldValue]:
        """§03 S8, in a worker thread — anchor matching is pure CPU."""
        warped = read.image_set.warp_succeeded if read.image_set is not None else False
        return self._extractor.extract(read.regions, read.side, doc_type, warped)

    # ------------------------------------------------------------------
    # S9 — normalization, per channel
    # ------------------------------------------------------------------

    async def _collect_exact(
        self, read: _ImageRead, candidates: Mapping[FieldKey, list[Candidate]]
    ) -> None:
        """Normalize QR and MRZ, which vouch for their whole read at one score."""
        if read.qr.available and read.qr.layout_recognized:
            _offer(candidates, await self._normalizer.normalize_channel(read.qr.fields, 1.0), FieldSource.QR)
        if read.mrz.available:
            normalized = await self._normalizer.normalize_channel(
                read.mrz.fields, read.mrz.confidence
            )
            _offer(candidates, normalized, FieldSource.MRZ)

    async def _collect_text(
        self,
        read: _ImageRead,
        candidates: Mapping[FieldKey, list[Candidate]],
        provenance: dict[FieldKey, RawFieldValue],
        tiers: dict[FieldKey, int],
    ) -> None:
        """Normalize the recognizer's readings — each carries its own score.

        ⭐ `provenance` keeps the raw text even when normalization rejected it.
        A field the user has to retype is exactly the field where seeing what
        the machine read is worth most (§5.3.4 `raw_value`).
        """
        for key, raw_value in read.raw.items():
            normalized = await self._normalizer.normalize(
                key, raw_value.text, raw_value.confidence
            )
            provenance[key] = raw_value
            if normalized.tier is not None:
                tiers[key] = normalized.tier
            if normalized.value is None:
                continue
            candidates[key].append(
                Candidate(
                    value=normalized.value,
                    source=FieldSource.OCR,
                    confidence=normalized.confidence,
                )
            )


# ======================================================================
# Module-level helpers — pure, so they are testable without a pipeline
# ======================================================================

_UNRESOLVED = SideClassification(
    front_index=0,
    back_index=1,
    confidence_a=0.0,
    confidence_b=0.0,
    swapped=False,
    verdict=SideVerdict.AMBIGUOUS,
)


def _sides_worth_reading(
    doc_types: Sequence[DocumentTypeSpec],
    candidates: Mapping[FieldKey, list[Candidate]],
) -> frozenset[CardSide]:
    """⭐ Lever 2 — which photos still have something to contribute.

    A side earns its whole-card pass when at least one field it could print is
    still missing or still weak. On a card where QR and MRZ both worked that
    leaves exactly one side: QR covers `id_number`, `full_name`,
    `date_of_birth` and `issue_date`, MRZ adds `expiry_date`, while
    `issue_place` has no exact channel at all and so always keeps its own side
    alive.

    ⚠️ The side→fields map is the **union over every candidate type**, because
    the generation is not known yet — and the two generations disagree about
    which side prints `expiry_date` (§7.4.7). Using the declared type here
    would let a mis-declared session skip the very pass that would have
    identified the card as the other generation.
    """
    wanted: set[CardSide] = set()
    for side in _BOTH_SIDES:
        for key in _fields_printed_on(doc_types, side):
            best = max((c.confidence for c in candidates.get(key, [])), default=0.0)
            if best < CORROBORATION_FLOOR:
                wanted.add(side)
                break
    return frozenset(wanted)


def _fields_printed_on(
    doc_types: Sequence[DocumentTypeSpec], side: CardSide
) -> frozenset[FieldKey]:
    """Read the side→field map straight out of `zone_map` (§4.4.1).

    Data, not code: a document type that prints its expiry somewhere else needs
    a new row, not a new branch here (NFR-10).
    """
    keys: set[FieldKey] = set()
    for doc_type in doc_types:
        for name, zone in doc_type.zone_map.items():
            if not isinstance(zone, Mapping) or zone.get("side") != side.value:
                continue
            try:
                keys.add(FieldKey(name))
            except ValueError:
                continue  # `mrz` is a zone, not a business field
    return frozenset(keys)


def _side_failure(
    classification: SideClassification,
    reads: Sequence[_ImageRead],
    started: float,
    diagnostics: list[Diagnostic],
) -> ExtractionResult | None:
    """Turn a non-`RESOLVED` verdict into the status §7.7 assigns it.

    ⭐ Neither outcome is `FAILED`: both are answerable by the user, and both
    leave `error_code` unset because nothing malfunctioned.
    """
    if classification.verdict is SideVerdict.RESOLVED:
        return None

    if classification.verdict is SideVerdict.DUPLICATE_SIDE:
        status = OcrSessionStatus.NEEDS_REUPLOAD
        diagnostics.append(_diag("S4", "DUPLICATE_SIDE", "Bạn đã tải hai ảnh của cùng một mặt."))
        same = CardSide.BACK if classification.front_index != 0 else CardSide.FRONT
        sides = {read.index: same for read in reads}
    else:
        status = OcrSessionStatus.NEEDS_MANUAL_ASSIGN
        diagnostics.append(_diag("S4", "SIDES_AMBIGUOUS", "Không xác định được đâu là mặt trước."))
        sides = {}

    return ExtractionResult(
        status=status,
        fields=empty_fields(),
        channel_summary=_summarize(reads),
        diagnostics=tuple(diagnostics),
        duration_ms=_elapsed_ms(started),
        detected_sides=sides,
    )


def _status_for(has_issues: bool) -> OcrSessionStatus:
    """⭐ Validation *errors* still mean the extraction COMPLETED.

    There is no `COMPLETED_WITH_ERRORS`, and that is deliberate: the run did
    its job — it read a card and found something wrong with it. What blocks the
    wizard is `validation_report.is_valid`, checked by the UI, not the session
    status (§8.2). Conflating the two would make "the pipeline worked" and "the
    card is usable" the same question, and they are not.
    """
    return (
        OcrSessionStatus.COMPLETED_WITH_WARNINGS if has_issues else OcrSessionStatus.COMPLETED
    )


def _assemble(
    candidates: Mapping[FieldKey, list[Candidate]],
    fused: Mapping[FieldKey, FusedField],
    provenance: Mapping[FieldKey, RawFieldValue],
    tiers: Mapping[FieldKey, int],
) -> dict[FieldKey, ExtractedField]:
    """All 6 keys, every time — §12.3's postcondition, enforced by construction."""
    assembled: dict[FieldKey, ExtractedField] = {}
    for key in FieldKey:
        winner = fused.get(key, EMPTY_FUSED)
        raw = provenance.get(key)
        assembled[key] = ExtractedField(
            fused=winner,
            raw_value=raw.text if raw is not None else None,
            bbox=raw.bbox if raw is not None else None,
            normalization_tier=tiers.get(key),
            candidates=_traces(candidates.get(key, ()), winner.value),
        )
    return assembled


def _offer(
    candidates: Mapping[FieldKey, list[Candidate]],
    normalized: Mapping[FieldKey, NormalizedValue],
    source: FieldSource,
) -> None:
    for key, value in normalized.items():
        if value.value is None:
            continue
        candidates[key].append(
            Candidate(value=value.value, source=source, confidence=value.confidence)
        )


def _traces(offers: Sequence[Candidate], winner: str | None) -> tuple[CandidateTrace, ...]:
    return tuple(
        CandidateTrace(
            source=offer.source, confidence=offer.confidence, agrees=offer.value == winner
        )
        for offer in offers
    )


def _summarize(reads: Sequence[_ImageRead]) -> ChannelSummary:
    """Fold both photos' channel outcomes into the `channels` block of §5.3.4."""
    qr = next((r.qr for r in reads if r.qr.available), None)
    mrz = next((r.mrz for r in reads if r.mrz.available), None)
    return ChannelSummary(
        qr_available=qr is not None,
        qr_layout_recognized=qr.layout_recognized if qr is not None else False,
        qr_attempts=sum(r.qr.attempts for r in reads),
        mrz_available=mrz is not None,
        mrz_checksum_valid=mrz.checksum_valid if mrz is not None else None,
        mrz_corrections_applied=mrz.corrections_applied if mrz is not None else 0,
        ocr_available=any(r.regions for r in reads),
        ocr_regions_detected=sum(len(r.regions) for r in reads),
        text_passes=sum(1 for r in reads if r.text_pass_ran),
    )


def _failed(
    error_code: str, started: float, diagnostics: tuple[Diagnostic, ...]
) -> ExtractionResult:
    return ExtractionResult(
        status=OcrSessionStatus.FAILED,
        fields=empty_fields(),
        diagnostics=diagnostics,
        duration_ms=_elapsed_ms(started),
        error_code=error_code,
    )


def _announce(progress: ProgressCallback, stage: str) -> None:
    """⭐ Every stage reports, even the ones that turn out to be no-ops (§12.3).

    A callback that raises is the caller's problem, not the run's: the whole
    point of the never-raises invariant is that a progress writer failing must
    not lose an extraction that already succeeded.
    """
    percent, message = _STAGE_PROGRESS[stage]
    try:
        progress(percent, message)
    except Exception:
        pass


def _diag(stage: str, code: str, message_vi: str, side: CardSide | None = None) -> Diagnostic:
    return Diagnostic(stage=stage, code=code, message_vi=message_vi, side=side)


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


__all__ = ["CORROBORATION_FLOOR", "ExtractionPipeline"]
