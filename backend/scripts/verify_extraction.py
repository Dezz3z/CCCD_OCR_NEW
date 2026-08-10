"""Measure S9 → S10 → S11 (normalize, fuse, validate) on real CCCD photos.

    python scripts/verify_extraction.py "C:/path/to/images"

⭐ **Cards are assembled from the images, not from filenames.** Every photo of
one card carries the same 12-digit citizen id — the front's QR and the back's
MRZ both print it — so matching on that number pairs the sample without a single
label. Cards that yield no id from either channel stay single-sided and are
counted separately rather than paired by guesswork.

⭐ **The False Confidence proxy is the number this script exists for.** Without
the Golden Set there is no ground truth, but there is something almost as
useful: QR and MRZ are exact channels, so wherever OCR *also* read a field, the
exact channel is the label. A field where OCR was ≥0.95 sure and disagreed with
QR/MRZ is a False Confidence event — the release-blocking KPI (§7.9), measured
here for the first time on the subset where it is measurable.

⚠️ Which is not the whole KPI. It says nothing about fields no exact channel
covers (`issue_place`, `issue_date` on a 2021 card), and its denominator is only
the overlap. Report it as what it is.
"""
from __future__ import annotations

import argparse
import importlib.util
import statistics
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from types import ModuleType

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from verify_qr_mrz import (
    DEFAULT_MODELS_DIR,
    GENERATION_THRESHOLD,
    IMAGE_SUFFIXES,
    MARKERS_2021,
    MARKERS_2024,
    build_recognizer,
    has_qr,
)

from cocas.domain.enums.card_side import CardSide
from cocas.domain.enums.field_key import FieldKey
from cocas.domain.enums.field_source import FieldSource
from cocas.domain.exceptions import OcrProcessingError
from cocas.domain.ports.ocr import (
    DocumentTypeSpec,
    IRegionRecognizer,
    OcrOptions,
    PreprocessProfile,
    TextRegion,
)
from cocas.domain.ports.persistence import AliasRecord
from cocas.domain.services.confidence_calculator import ConfidenceCalculator
from cocas.domain.services.field_fusion_service import (
    OCR_FIELD_FACTORS,
    Candidate,
    FieldFusionService,
    FusionContext,
)
from cocas.domain.services.field_normalizer import FieldNormalizer, NormalizedValue
from cocas.domain.services.issue_place_normalizer import IssuePlaceNormalizer
from cocas.domain.validation import (
    OcrValidationTarget,
    RuleContext,
    RuleSetKey,
    Severity,
    ValidationEngine,
)
from cocas.infrastructure.ocr.channels.mrz_reader import Td1MrzReader
from cocas.infrastructure.ocr.channels.qr_decoder import ZxingQrDecoder
from cocas.infrastructure.ocr.extraction.zone_anchor_extractor import ZoneAndAnchorExtractor
from cocas.infrastructure.ocr.preprocessing.opencv_preprocessor import OpenCvPreprocessor
from cocas.infrastructure.ocr.text_matching import similarity

_VERSIONS = Path(__file__).resolve().parent.parent / "migrations" / "versions"
FALSE_CONFIDENCE_FLOOR = 0.95


def _load(filename: str) -> ModuleType:
    """Read a seeded document type straight from its migration — no second copy."""
    spec = importlib.util.spec_from_file_location(filename, _VERSIONS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _doc_type(module: ModuleType, code: str, name: str) -> DocumentTypeSpec:
    return DocumentTypeSpec(
        code=code,
        name=name,
        field_schema=[],
        zone_map=module._ZONE_MAP,
        anchor_patterns=module._ANCHOR_PATTERNS,
        has_qr=True,
        has_mrz=True,
        is_ocr_supported=True,
        expected_aspect_ratio=1.585,
    )


# The two alias rows §4.4.14 seeds for `issue_place`, enough for tier 2/4 here.
SEED_ALIASES = [
    AliasRecord(
        id=1,
        field_key="issue_place",
        canonical_value="CỤC CẢNH SÁT QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI",
        match_tier=4,
        assigned_confidence=0.60,
        keywords=("CUC", "CANH", "SAT"),
    ),
    AliasRecord(
        id=2,
        field_key="issue_place",
        canonical_value="BỘ CÔNG AN",
        match_tier=4,
        assigned_confidence=0.60,
        keywords=("BO", "CONG", "AN"),
    ),
]


class StaticAliasRepository:
    """`IAliasRepository` over a fixed list — the seed rows, without a database."""

    async def find_by_alias(
        self, _document_type_code: str, _field_key: str, alias_normalized: str
    ) -> AliasRecord | None:
        return next(
            (a for a in SEED_ALIASES if a.alias_normalized == alias_normalized), None
        )

    async def list_active(self, _document_type_code: str, field_key: str) -> list[AliasRecord]:
        return [a for a in SEED_ALIASES if a.field_key == field_key]


@dataclass
class ImageRead:
    """One photo, after every channel has had its turn."""

    path: Path
    generation: str
    side: CardSide
    citizen_id: str | None
    candidates: dict[FieldKey, list[Candidate]] = field(default_factory=lambda: defaultdict(list))
    seconds: float = 0.0
    # OCR value vs the exact channel's value, per field — the proxy's raw material.
    #
    # ⭐ The confidence recorded here is the one **fusion would score**, i.e. after
    # rule 2's per-field factor — not the recognizer's raw score. False Confidence
    # asks "was the number shown to the user too high", and the number shown is the
    # fused one. Recording the raw score puts every 0.97 name read into the ≥0.95
    # bucket when fusion would have scored it 0.73 and sent it to review.
    comparisons: list[tuple[FieldKey, float, bool]] = field(default_factory=list)
    ocr_error: str | None = None
    """Set when the OCR channel gave up on this image — QR/MRZ results still stand."""


async def read_image(
    path: Path,
    preprocessor: OpenCvPreprocessor,
    profile: PreprocessProfile,
    qr_decoder: ZxingQrDecoder,
    mrz_reader: Td1MrzReader,
    recognizer: IRegionRecognizer,
    extractor: ZoneAndAnchorExtractor,
    normalizer: FieldNormalizer,
    doc_types: dict[str, DocumentTypeSpec],
) -> ImageRead | None:
    started = time.perf_counter()
    try:
        image_set = preprocessor.prepare(path.read_bytes(), None, profile)
    except OcrProcessingError:
        return None

    qr = qr_decoder.decode(image_set)
    mrz = mrz_reader.read(image_set, doc_types["2021"])
    side = CardSide.BACK if mrz.available else CardSide.FRONT

    read = ImageRead(path=path, generation="?", side=side, citizen_id=None)

    exact: dict[FieldKey, str] = {}
    if qr.available and qr.layout_recognized:
        for key, value in (await normalizer.normalize_channel(qr.fields, 1.0)).items():
            _add(read, key, value, FieldSource.QR, exact)
    if mrz.available:
        for key, value in (
            await normalizer.normalize_channel(mrz.fields, mrz.confidence)
        ).items():
            _add(read, key, value, FieldSource.MRZ, exact)

    # ⭐⭐ **Exactly one whole-card pass**, on the `v3` variant §7.4.1 assigns to
    # the text channel — and both the card generation and all six fields are read
    # out of it. This is the P3 recipe of §7.4.6 finding 20 ("recognize the whole
    # card once, then reuse the regions"), and measuring it any other way would
    # measure a pipeline nobody intends to build. The first version of this script
    # paid for two passes and took 28–45 s per image on a 4 GB machine.
    #
    # ⚠️ Caught, not propagated: §7.7 makes a dead OCR channel a *degradation*,
    # not a failure. A card that still has its QR is still worth reporting, and a
    # script that dies on one slow image measures nothing about the other 52.
    try:
        regions = recognizer.recognize(image_set.v3, OcrOptions())  # type: ignore[attr-defined]
    except OcrProcessingError as exc:
        read.ocr_error = type(exc).__name__
        read.citizen_id = exact.get(FieldKey.ID_NUMBER)
        read.seconds = time.perf_counter() - started
        return read

    read.generation = _generation_from(regions, side, has_qr(qr))
    doc_type = doc_types.get(read.generation, doc_types["2021"])
    raw = extractor.extract(regions, side, doc_type, image_set.warp_succeeded)
    for key, raw_value in raw.items():
        normalized = await normalizer.normalize(key, raw_value.text, raw_value.confidence)
        if normalized.value is None:
            continue
        read.candidates[key].append(
            Candidate(value=normalized.value, source=FieldSource.OCR, confidence=normalized.confidence)
        )
        if key in exact:
            scored = normalized.confidence * OCR_FIELD_FACTORS.get(key, 1.0)
            read.comparisons.append((key, scored, normalized.value == exact[key]))

    read.citizen_id = exact.get(FieldKey.ID_NUMBER)
    read.seconds = time.perf_counter() - started
    return read


def _generation_from(regions: list[TextRegion], side: CardSide, qr_read: bool) -> str:
    """Which generation, from text already recognized — no second pass.

    Same markers and same structural override as `verify_qr_mrz._generation_of`
    (an image carrying both a QR and an MRZ can only be a Căn cước 2024 back);
    only the input differs, so the two scripts still agree about the sample.
    """
    if side is CardSide.BACK and qr_read:
        return "2024"
    lines = [region.text for region in regions if region.text.strip()]
    hits_2024 = _marker_hits(lines, MARKERS_2024)
    hits_2021 = _marker_hits(lines, MARKERS_2021)
    if hits_2024 > hits_2021:
        return "2024"
    return "2021" if hits_2021 > hits_2024 else "?"


def _marker_hits(lines: list[str], markers: tuple[str, ...]) -> int:
    return sum(
        any(similarity(line, marker) >= GENERATION_THRESHOLD for line in lines)
        for marker in markers
    )


def _add(
    read: ImageRead,
    key: FieldKey,
    value: NormalizedValue,
    source: FieldSource,
    exact: dict[FieldKey, str],
) -> None:
    if value.value is None:
        return
    read.candidates[key].append(
        Candidate(value=value.value, source=source, confidence=value.confidence)
    )
    exact.setdefault(key, value.value)


async def run(folder: Path, models_dir: Path, *, verbose: bool) -> int:
    images = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    if not images:
        print(f"No images found in {folder}")
        return 1

    recognizer = build_recognizer(models_dir)
    if recognizer is None:
        return 1

    doc_types = {
        "2021": _doc_type(_load("20260811_003_seed_doctype.py"), "CCCD_CHIP", "CCCD gắn chip"),
        "2024": _doc_type(
            _load("20260811_009_seed_doctype_2024.py"), "CAN_CUOC_2024", "Căn cước 2024"
        ),
    }
    normalizer = FieldNormalizer(IssuePlaceNormalizer(StaticAliasRepository()))  # type: ignore[arg-type]
    preprocessor = OpenCvPreprocessor()
    profile = PreprocessProfile()
    qr_decoder = ZxingQrDecoder()
    mrz_reader = Td1MrzReader(recognizer)
    extractor = ZoneAndAnchorExtractor()

    reads: list[ImageRead] = []
    for path in images:
        result = await read_image(
            path, preprocessor, profile, qr_decoder, mrz_reader, recognizer,
            extractor, normalizer, doc_types,
        )
        if result is None:
            print(f"{path.name[:44]:46} PREPROCESS FAILED")
            continue
        reads.append(result)
        note = f" OCR:{result.ocr_error}" if result.ocr_error else ""
        print(f"{path.name[:44]:46} {result.generation}-{result.side.value:5} "
              f"{len(result.candidates)} fields  {result.seconds:.1f}s{note}")

    _report(reads, verbose=verbose)
    return 0


@dataclass
class Totals:
    """Everything the printout needs, gathered in one pass over the cards."""

    value_counts: Counter[FieldKey] = field(default_factory=Counter)
    source_counts: Counter[tuple[FieldKey, str]] = field(default_factory=Counter)
    review_counts: Counter[FieldKey] = field(default_factory=Counter)
    confidences: dict[FieldKey, list[float]] = field(default_factory=lambda: defaultdict(list))
    code_counts: Counter[str] = field(default_factory=Counter)
    overalls: list[float] = field(default_factory=list)
    blocked: int = 0


def _score_card(
    citizen_id: str, group: list[ImageRead], totals: Totals, *, verbose: bool
) -> None:
    """Fuse one card's images, validate the result, and fold it into `totals`."""
    merged: dict[FieldKey, list[Candidate]] = defaultdict(list)
    for read in group:
        for key, candidates in read.candidates.items():
            merged[key].extend(candidates)

    fused = FieldFusionService().fuse(merged, FusionContext())
    overall = ConfidenceCalculator().overall(fused)
    totals.overalls.append(overall)

    sides = {read.side for read in group}
    target = OcrValidationTarget(
        fields=fused,
        has_front_image=CardSide.FRONT in sides,
        has_back_image=CardSide.BACK in sides,
        duplicate_side=len(group) > len(sides),
    )
    report = ValidationEngine().validate(
        target, RuleSetKey.OCR_RESULT, RuleContext(today=date.today())
    )
    if not report.is_valid:
        totals.blocked += 1
    for issue in report.issues:
        totals.code_counts[issue.code] += 1

    for key, value in fused.items():
        if value.value is None:
            continue
        totals.value_counts[key] += 1
        totals.source_counts[(key, value.source.value)] += 1
        totals.confidences[key].append(value.confidence)
        if value.needs_review:
            totals.review_counts[key] += 1

    if verbose:
        print(f"\n  card {citizen_id[:3]}…{citizen_id[-3:]}  overall {overall:.2f}  "
              f"{'BLOCKED' if not report.is_valid else 'ok'}")
        for issue in report.issues:
            print(f"    {issue.severity.value:8} {issue.code}  {issue.message_vi}")


def _print_false_confidence(reads: list[ImageRead]) -> None:
    """⭐ §7.9's release-blocking KPI, on the subset where a label exists."""
    print("\n⭐ False Confidence proxy (§7.9 — the release-blocking KPI)")
    checked = [(k, conf, ok) for read in reads for k, conf, ok in read.comparisons]
    high = [(k, ok) for k, conf, ok in checked if conf >= FALSE_CONFIDENCE_FLOOR]
    wrong_high = [k for k, ok in high if not ok]

    if high:
        print(f"  OCR fields at >={FALSE_CONFIDENCE_FLOOR:.2f} with an exact channel to check "
              f"against: {len(high)}")
        print(f"  of those, disagreeing: {len(wrong_high)} "
              f"({len(wrong_high) / len(high) * 100:.1f}%)   target <=0.5%")
        if wrong_high:
            print(f"  fields involved: {dict(Counter(k.value for k in wrong_high))}")
    else:
        print(f"  no OCR field reached {FALSE_CONFIDENCE_FLOOR:.2f} where an exact channel "
              "could check it")

    if checked:
        agree = sum(1 for _, _, ok in checked if ok)
        print(f"  (OCR vs QR/MRZ overall: {agree}/{len(checked)} agree "
              f"= {agree / len(checked) * 100:.1f}%)")


def _report(reads: list[ImageRead], *, verbose: bool) -> None:
    # ⭐ Assemble cards by the id number both exact channels print.
    by_id: dict[str, list[ImageRead]] = defaultdict(list)
    orphans = [read for read in reads if read.citizen_id is None]
    for read in reads:
        if read.citizen_id is not None:
            by_id[read.citizen_id].append(read)

    print(f"\n{'=' * 70}")
    print(f"{len(reads)} images read | {len(by_id)} cards assembled by citizen id "
          f"| {len(orphans)} images with no exact-channel id")
    paired = sum(1 for group in by_id.values() if len(group) > 1)
    print(f"  of those cards, {paired} have both sides")

    totals = Totals()
    for citizen_id, group in sorted(by_id.items()):
        _score_card(citizen_id, group, totals, verbose=verbose)

    value_counts = totals.value_counts
    source_counts = totals.source_counts
    review_counts = totals.review_counts
    confidences = totals.confidences
    code_counts = totals.code_counts
    overalls = totals.overalls
    blocked = totals.blocked

    cards = max(len(by_id), 1)
    print(f"\nPer field, across {len(by_id)} cards")
    print(f"  {'field':<15}{'read':>6}{'rate':>8}{'mean conf':>11}{'review':>8}  winning source")
    for key in FieldKey:
        read_n = value_counts[key]
        mean = statistics.mean(confidences[key]) if confidences[key] else 0.0
        sources = {
            source: count for (k, source), count in source_counts.items() if k is key
        }
        print(f"  {key.value:<15}{read_n:>6}{read_n / cards * 100:>7.0f}%{mean:>11.2f}"
              f"{review_counts[key]:>8}  {sources}")

    _print_false_confidence(reads)

    print("\nValidation (§8.4), issues raised per card")
    for code, count in sorted(code_counts.items()):
        severity = _severity_of(code)
        print(f"  {code}  {severity:<8}{count:>4}")
    print(f"  cards blocked by an ERROR: {blocked}/{len(by_id)}")

    if overalls:
        print(f"\nOverall confidence  mean {statistics.mean(overalls):.2f}  "
              f"min {min(overalls):.2f}  max {max(overalls):.2f}")
    times = sorted(read.seconds for read in reads)
    if times:
        p95 = times[min(int(len(times) * 0.95), len(times) - 1)]
        print(f"Per-image time      mean {statistics.mean(times):.1f}s  p95 {p95:.1f}s  "
              f"(budget: 9s per PAIR)")
    failures = Counter(read.ocr_error for read in reads if read.ocr_error)
    if failures:
        print(f"OCR channel gave up on {sum(failures.values())} image(s): {dict(failures)}")


def _severity_of(code: str) -> str:
    for rule_code, severity in _SEVERITY_BY_CODE.items():
        if rule_code == code:
            return severity
    return "?"


_SEVERITY_BY_CODE = {
    f"V-OCR-{n:03d}": s
    for n, s in {
        1: Severity.ERROR, 2: Severity.ERROR, 3: Severity.ERROR, 4: Severity.WARNING,
        5: Severity.ERROR, 6: Severity.ERROR, 7: Severity.ERROR, 8: Severity.ERROR,
        9: Severity.ERROR, 10: Severity.WARNING, 11: Severity.WARNING, 12: Severity.ERROR,
        13: Severity.WARNING, 14: Severity.INFO, 15: Severity.INFO, 16: Severity.ERROR,
        17: Severity.ERROR, 18: Severity.WARNING, 19: Severity.ERROR, 20: Severity.WARNING,
        21: Severity.WARNING, 22: Severity.WARNING, 23: Severity.WARNING,
    }.items()
}
_SEVERITY_BY_CODE = {code: sev.value for code, sev in _SEVERITY_BY_CODE.items()}


def main() -> int:
    import asyncio

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, help="Folder of CCCD images")
    parser.add_argument("--models", type=Path, default=DEFAULT_MODELS_DIR)
    parser.add_argument("--verbose", action="store_true", help="print every card's issues")
    args = parser.parse_args()
    if not args.folder.is_dir():
        print(f"Not a folder: {args.folder}")
        return 1
    return asyncio.run(run(args.folder, args.models, verbose=args.verbose))


if __name__ == "__main__":
    raise SystemExit(main())
