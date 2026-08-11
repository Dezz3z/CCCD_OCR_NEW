"""Run the real `ExtractionPipeline` over a folder of CCCD photos.

    python scripts/verify_pipeline.py "C:/path/to/images"

⭐ **This measures the thing P3 actually ships**, where `verify_extraction.py`
measured the parts. The numbers that matter here are the ones only the assembled
pipeline can produce:

* **text passes** — the whole-card recognitions actually paid for, against the
  2 per pair a naive orchestration would cost. This is lever 2 of §12.3, and it
  is the only lever that moves seconds rather than milliseconds.
* **seconds per pair** — the budget is stated per pair (≤9 s p95, NFR-01) and
  every earlier measurement was per image, so this is the first number directly
  comparable to the target.
* **generation selection** — how often Port 19 agrees with the marker labels the
  earlier scripts assign, and how often it declines to answer.

⚠️ **Cards are assembled by the 12-digit id both exact channels print, never by
filename**, exactly as `verify_extraction.py` does — the sample folder is not in
front/back order and its names carry no card identity. The first version of this
script paired adjacent filenames and produced numbers that looked like pipeline
faults but were harness faults: 23 of 26 "pairs" raised `SOURCE_CONFLICT`,
`id_number` averaged 0.68 confidence, and not one Căn cước 2024 was recognized —
all because two photos of two different people had been handed to `execute()`
as one card.

⚠️ The pairing pre-pass is **harness overhead and is not timed**. The real app
never needs it: the user uploads two photos and says they belong together.

⚠️ Still not a KPI run. The sample is dev data, not the Golden Set, so treat
accuracy here as a regression check against the previous script's numbers, not
as an acceptance measurement.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import statistics
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from verify_extraction import SEED_ALIASES, StaticAliasRepository
from verify_qr_mrz import DEFAULT_MODELS_DIR, IMAGE_SUFFIXES, build_recognizer

from cocas.application.dto.extraction import ExtractionResult
from cocas.application.pipelines.extraction_pipeline import ExtractionPipeline
from cocas.domain.enums.field_key import FieldKey
from cocas.domain.enums.ocr_session_status import OcrSessionStatus
from cocas.domain.exceptions import OcrProcessingError
from cocas.domain.ports.ocr import (
    DocumentTypeSpec,
    OcrOptions,
    PreprocessProfile,
)
from cocas.domain.services.field_normalizer import FieldNormalizer
from cocas.domain.services.issue_place_normalizer import IssuePlaceNormalizer
from cocas.infrastructure.ocr.channels.mrz_reader import Td1MrzReader
from cocas.infrastructure.ocr.channels.qr_decoder import ZxingQrDecoder
from cocas.infrastructure.ocr.classification.document_type_selector import (
    MarkerDocumentTypeSelector,
)
from cocas.infrastructure.ocr.classification.side_classifier import (
    HeuristicSideClassifier,
)
from cocas.infrastructure.ocr.extraction.zone_anchor_extractor import (
    ZoneAndAnchorExtractor,
)
from cocas.infrastructure.ocr.preprocessing.opencv_preprocessor import (
    OpenCvPreprocessor,
)
from cocas.infrastructure.system.clock import SystemClock

_VERSIONS = Path(__file__).resolve().parent.parent / "migrations" / "versions"

# The budget of NFR-01, per pair. Printed alongside every timing so the number
# is never read without the target next to it.
PAIR_BUDGET_SECONDS = 9.0

# What a naive orchestration would cost: recognize both photos, every time.
PASSES_WITHOUT_LEVER = 2

# Statuses that mean the run got as far as the text channel. Everything else
# stopped at S3 or S4 and must stay out of the timing and lever denominators.
_REACHED_S7 = frozenset(
    {OcrSessionStatus.COMPLETED, OcrSessionStatus.COMPLETED_WITH_WARNINGS}
)


def _load(filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(filename, _VERSIONS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _doc_types() -> list[DocumentTypeSpec]:
    """Both generations, read out of the migrations that seed them.

    ⭐ Including `identity_markers` from `20260811_010` — the same rows the app
    will load from `document_type`, so the selector is measured on real data
    rather than on a fixture written to make it pass.
    """
    markers = _load("20260811_010_markers_tier5.py")._MARKERS
    specs = []
    for filename, code, name in (
        ("20260811_003_seed_doctype.py", "CCCD_CHIP", "CCCD gắn chip"),
        ("20260811_009_seed_doctype_2024.py", "CAN_CUOC_2024", "Căn cước 2024"),
    ):
        module = _load(filename)
        specs.append(
            DocumentTypeSpec(
                code=code,
                name=name,
                field_schema=[],
                zone_map=module._ZONE_MAP,
                anchor_patterns=module._ANCHOR_PATTERNS,
                has_qr=True,
                has_mrz=True,
                is_ocr_supported=True,
                expected_aspect_ratio=1.585,
                identity_markers=tuple(markers[code]),
            )
        )
    return specs


@dataclass
class PairRun:
    """One `execute()` call and what it cost."""

    names: tuple[str, str]
    result: ExtractionResult
    seconds: float


@dataclass
class Totals:
    passes: int = 0
    pairs: int = 0
    reached_s7: int = 0
    """⭐ The denominator lever 2 must be measured against. A pair that stopped
    at S4 pays 0 passes, and counting it as "2 saved" credits the lever with
    work the run never had to do — the denominator trap of §7.4.7 again."""
    generations: Counter[str] = field(default_factory=Counter)
    statuses: Counter[str] = field(default_factory=Counter)
    value_counts: Counter[FieldKey] = field(default_factory=Counter)
    review_counts: Counter[FieldKey] = field(default_factory=Counter)
    confidences: dict[FieldKey, list[float]] = field(default_factory=lambda: defaultdict(list))
    codes: Counter[str] = field(default_factory=Counter)
    blocked: int = 0
    overalls: list[float] = field(default_factory=list)
    seconds: list[float] = field(default_factory=list)


def _assemble_pairs(
    images: list[Path],
    preprocessor: OpenCvPreprocessor,
    qr_decoder: ZxingQrDecoder,
    mrz_reader: Td1MrzReader,
    doc_type: DocumentTypeSpec,
) -> list[tuple[Path, Path]]:
    """⭐ Group photos into cards by the id number QR and MRZ both print.

    Untimed harness work — see the module docstring. Reads only the two exact
    channels, never a whole-card pass, so it costs a fraction of the run it is
    setting up.
    """
    by_id: dict[str, list[Path]] = defaultdict(list)
    unpaired: list[Path] = []
    profile = PreprocessProfile()

    for path in images:
        citizen_id = None
        try:
            image_set = preprocessor.prepare(path.read_bytes(), None, profile)
            qr = qr_decoder.decode(image_set)
            if qr.available and qr.layout_recognized:
                citizen_id = qr.fields.get(FieldKey.ID_NUMBER)
            if citizen_id is None:
                mrz = mrz_reader.read(image_set, doc_type)
                if mrz.available:
                    citizen_id = mrz.fields.get(FieldKey.ID_NUMBER)
        except (OcrProcessingError, OSError):
            pass
        if citizen_id is None:
            unpaired.append(path)
        else:
            by_id[citizen_id].append(path)

    pairs = [(group[0], group[1]) for group in by_id.values() if len(group) == 2]
    singles = [g for g in by_id.values() if len(g) == 1]
    print(
        f"{len(images)} photos → {len(pairs)} complete cards"
        f" · {len(singles)} one-sided · {len(unpaired)} with no id from either channel"
    )
    if len(pairs) < 2:
        print("⚠️  Too few complete cards to measure anything. Is this the right folder?")
    return pairs


async def run(folder: Path, models_dir: Path, *, verbose: bool) -> int:
    images = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    if not images:
        print(f"No images found in {folder}")
        return 1

    recognizer = build_recognizer(models_dir)
    if recognizer is None:
        return 1

    doc_types = _doc_types()
    preprocessor = OpenCvPreprocessor()
    qr_decoder = ZxingQrDecoder()
    mrz_reader = Td1MrzReader(recognizer)
    pipeline = ExtractionPipeline(
        preprocessor=preprocessor,
        side_classifier=HeuristicSideClassifier(qr_decoder, recognizer),
        qr_decoder=qr_decoder,
        mrz_reader=mrz_reader,
        engine=recognizer,
        extractor=ZoneAndAnchorExtractor(),
        doc_type_selector=MarkerDocumentTypeSelector(),
        normalizer=FieldNormalizer(IssuePlaceNormalizer(StaticAliasRepository())),  # type: ignore[arg-type]
        clock=SystemClock(),
    )
    print(f"{len(SEED_ALIASES)} alias rows loaded · {len(doc_types)} document types")
    pairs = _assemble_pairs(images, preprocessor, qr_decoder, mrz_reader, doc_types[0])
    print()

    runs: list[PairRun] = []
    for first, second in pairs:
        started = time.perf_counter()
        result = await pipeline.execute(
            first.read_bytes(), second.read_bytes(), doc_types
        )
        elapsed = time.perf_counter() - started
        runs.append(PairRun((first.name, second.name), result, elapsed))
        _print_pair(runs[-1])

    _report(runs, verbose=verbose)
    return 0


def _print_pair(run_: PairRun) -> None:
    result = run_.result
    over = "  ⚠️ OVER" if run_.seconds > PAIR_BUDGET_SECONDS else ""
    print(
        f"{run_.names[0][:26]:28}{run_.names[1][:26]:28}"
        f"{result.status.value:26}{result.card_generation or '?':14}"
        f"{result.fields_read}/6  {result.channel_summary.text_passes} pass  "
        f"{run_.seconds:5.1f}s{over}"
    )


def _tally(runs: list[PairRun]) -> Totals:
    totals = Totals()
    for run_ in runs:
        result = run_.result
        totals.pairs += 1
        totals.passes += result.channel_summary.text_passes
        totals.statuses[result.status.value] += 1
        totals.generations[result.card_generation or "?"] += 1
        totals.seconds.append(run_.seconds)
        if result.status in _REACHED_S7:
            totals.reached_s7 += 1
        if result.status is OcrSessionStatus.FAILED:
            continue
        totals.overalls.append(result.overall_confidence)
        if not result.validation_report.is_valid:
            totals.blocked += 1
        for issue in result.validation_report.issues:
            totals.codes[issue.code] += 1
        _tally_fields(result, totals)
    return totals


def _tally_fields(result: ExtractionResult, totals: Totals) -> None:
    for key, extracted in result.fields.items():
        if extracted.value is None:
            continue
        totals.value_counts[key] += 1
        totals.confidences[key].append(extracted.confidence)
        if extracted.needs_review:
            totals.review_counts[key] += 1


def _print_lever_two(totals: Totals) -> None:
    print("⭐ Lever 2 — whole-card passes actually paid for")
    naive = totals.reached_s7 * PASSES_WITHOUT_LEVER
    saved = naive - totals.passes
    print(f"  {totals.reached_s7}/{totals.pairs} pairs reached the text channel at all")
    if naive:
        print(f"  paid {totals.passes} of {naive}  ({saved} skipped = "
              f"{saved / naive * 100:.0f}% of the recognition work)")
        print(f"  passes per pair that got there: {totals.passes / totals.reached_s7:.2f} of 2")


def _print_timing(runs: list[PairRun]) -> None:
    print("\n⭐ Seconds per PAIR — the unit the budget is stated in")
    # ⚠️ Only the pairs that ran the whole chain. A pair rejected at S4 costs
    # ~1 s and would flatter every statistic below it.
    worked = sorted(r.seconds for r in runs if r.result.status in _REACHED_S7)
    if not worked:
        return
    p95 = worked[min(int(len(worked) * 0.95), len(worked) - 1)]
    over = sum(1 for s in worked if s > PAIR_BUDGET_SECONDS)
    print(f"  over the {len(worked)} pairs that ran the full chain:")
    print(f"  mean {statistics.mean(worked):.1f}s  median {statistics.median(worked):.1f}s  "
          f"p95 {p95:.1f}s  max {max(worked):.1f}s")
    print(f"  budget {PAIR_BUDGET_SECONDS:.0f}s — {over}/{len(worked)} pairs over it "
          f"{'✅' if p95 <= PAIR_BUDGET_SECONDS else '🔴'}")
    print("  ⚠️ one run of one sample on one machine — p95 has moved by a "
          "factor of 1.7 between identical runs before (progress.md)")


def _print_fields(totals: Totals) -> None:
    print(f"\nPer field, across {totals.pairs} pairs")
    print(f"  {'field':<15}{'read':>6}{'rate':>8}{'mean conf':>11}{'review':>8}")
    for key in FieldKey:
        read_n = totals.value_counts[key]
        mean = statistics.mean(totals.confidences[key]) if totals.confidences[key] else 0.0
        print(f"  {key.value:<15}{read_n:>6}{read_n / max(totals.pairs, 1) * 100:>7.0f}%"
              f"{mean:>11.2f}{totals.review_counts[key]:>8}")


def _report(runs: list[PairRun], *, verbose: bool) -> None:
    totals = _tally(runs)

    print(f"\n{'=' * 78}")
    print(f"{totals.pairs} pairs through the real pipeline\n")
    _print_lever_two(totals)
    _print_timing(runs)

    print("\n⭐ Port 19 — which generation each pair was judged to be")
    for code, count in totals.generations.most_common():
        print(f"  {code:16}{count:>4}")

    print("\nStatus")
    for status, count in totals.statuses.most_common():
        print(f"  {status:28}{count:>4}")

    _print_fields(totals)

    if totals.codes:
        print("\nValidation issues raised")
        for code, count in sorted(totals.codes.items()):
            print(f"  {code}{count:>5}")
        print(f"  pairs blocked by an ERROR: {totals.blocked}/{totals.pairs}")

    if totals.overalls:
        print(f"\nOverall confidence  mean {statistics.mean(totals.overalls):.2f}  "
              f"min {min(totals.overalls):.2f}  max {max(totals.overalls):.2f}")

    if verbose:
        print("\nDiagnostics raised")
        every = Counter(d.code for run_ in runs for d in run_.result.diagnostics)
        for code, count in every.most_common():
            print(f"  {code:28}{count:>4}")


async def selector_sweep(folder: Path, models_dir: Path) -> int:
    """⭐ Measure Port 19 alone, on every photo, both generations.

    Exists because the id-based pairing above **structurally cannot assemble a
    Căn cước 2024**: that generation prints its QR beside its MRZ on the back
    (§7.4.7), so its front carries no exact channel and yields no id to group
    on. Every card the paired run measures is therefore a 2021 card, and the
    selector — the one component whose entire job is telling the generations
    apart — goes completely unexercised by it.

    The reference label is `verify_extraction._generation_from`, the
    marker-vote already measured on this sample. Two differences are the point
    of the comparison:

    * that function has a **structural override** (an image carrying both a QR
      and an MRZ can only be a 2024 back) which Port 19 deliberately lacks,
      because Port 19 is handed regions and nothing else;
    * that function pools one photo's lines, while the pipeline pools both.

    So a disagreement here is information, not a failure: it says how often the
    text alone is not enough and the pipeline falls back to the declared type.
    """
    from verify_extraction import _generation_from
    from verify_qr_mrz import has_qr

    from cocas.domain.enums.card_side import CardSide

    images = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    recognizer = build_recognizer(models_dir)
    if recognizer is None:
        return 1

    doc_types = _doc_types()
    preprocessor = OpenCvPreprocessor()
    qr_decoder = ZxingQrDecoder()
    mrz_reader = Td1MrzReader(recognizer)
    selector = MarkerDocumentTypeSelector()
    profile = PreprocessProfile()

    agree = Counter[str]()
    matrix: Counter[tuple[str, str]] = Counter()
    for path in images:
        try:
            image_set = preprocessor.prepare(path.read_bytes(), None, profile)
            qr = qr_decoder.decode(image_set)
            mrz = mrz_reader.read(image_set, doc_types[0])
            side = CardSide.BACK if mrz.available else CardSide.FRONT
            regions = recognizer.recognize(image_set.v3, OcrOptions())
        except (OcrProcessingError, OSError) as exc:
            print(f"{path.name[:44]:46} SKIPPED ({type(exc).__name__})")
            continue

        label = _generation_from(regions, side, has_qr(qr))
        picked = selector.select(regions, doc_types)
        verdict = {"CCCD_CHIP": "2021", "CAN_CUOC_2024": "2024"}.get(
            picked.code if picked else "", "?"
        )
        matrix[(label, verdict)] += 1
        agree["same" if label == verdict else "differ"] += 1
        flag = "" if label == verdict else "   ← differs"
        print(f"{path.name[:44]:46} label={label:5} port19={verdict:5}{flag}")

    print(f"\n{'=' * 70}")
    print("⭐ Port 19 vs the marker vote already measured on this sample")
    total = sum(agree.values())
    print(f"  agree {agree['same']}/{total}  differ {agree['differ']}/{total}")
    print("\n  marker label -> Port 19 verdict")
    for (label, verdict), count in sorted(matrix.items()):
        note = ""
        if verdict == "?" and label != "?":
            note = "  ← text alone was not enough; pipeline keeps the declared type"
        elif label != verdict and verdict != "?":
            note = "  🔴 disagreement on a decided card"
        print(f"    {label:6} → {verdict:6}{count:>4}{note}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, help="Folder of CCCD images")
    parser.add_argument("--models", type=Path, default=DEFAULT_MODELS_DIR)
    parser.add_argument("--verbose", action="store_true", help="also list every diagnostic")
    parser.add_argument(
        "--selector-sweep",
        action="store_true",
        help="measure Port 19 alone on every photo (the only way to reach 2024 cards)",
    )
    args = parser.parse_args()
    if not args.folder.is_dir():
        print(f"Not a folder: {args.folder}")
        return 1
    if args.selector_sweep:
        return asyncio.run(selector_sweep(args.folder, args.models))
    return asyncio.run(run(args.folder, args.models, verbose=args.verbose))


if __name__ == "__main__":
    raise SystemExit(main())
