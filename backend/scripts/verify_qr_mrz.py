"""Measure the QR and MRZ channels against a folder of real CCCD photos.

⭐ This is the script that decides whether the §7.4.3 / §7.4.4 targets are met.
Run it against the labelled Golden Set once that exists; until then it reports
against whatever sample folder is handed to it and the rates are indicative
only — the front/back split is unknown, so the QR denominator is not the number
of images.

    python scripts/verify_qr_mrz.py "C:/path/to/images"

The MRZ channel needs an `IRegionRecognizer`. Without one (before the PaddleOCR
adapter lands in week 3) the MRZ section reports as skipped rather than zero,
so a missing engine never looks like a failing channel.
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cocas.domain.enums.field_key import FieldKey
from cocas.domain.exceptions import OcrProcessingError
from cocas.domain.ports.ocr import (
    DocumentTypeSpec,
    IRegionRecognizer,
    PreprocessProfile,
)
from cocas.infrastructure.ocr.channels.mrz_reader import Td1MrzReader
from cocas.infrastructure.ocr.channels.qr_decoder import ZxingQrDecoder
from cocas.infrastructure.ocr.preprocessing.opencv_preprocessor import (
    OpenCvPreprocessor,
)

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

CCCD_CHIP = DocumentTypeSpec(
    code="CCCD_CHIP",
    name="Căn cước công dân gắn chip",
    field_schema=[],
    # ⭐ Calibrated 2026-08-09 against 20 real backs (was 0.82/0.16, which sat
    # below the first two MRZ lines and read the address block instead).
    zone_map={"mrz": {"x": 0.02, "y": 0.62, "w": 0.96, "h": 0.36}},
    anchor_patterns={},
    has_qr=True,
    has_mrz=True,
    is_ocr_supported=True,
    expected_aspect_ratio=1.585,
)


DEFAULT_MODELS_DIR = Path(__file__).resolve().parent.parent / "resources" / "ocr-models"


def build_recognizer(models_dir: Path) -> IRegionRecognizer | None:
    """Warm up the real engine, or return None when its models are not installed.

    A missing model set reports as "skipped", never as a failing channel — see
    `scripts/fetch_ocr_models.py` for how to populate it.
    """
    from cocas.infrastructure.ocr.engines import PaddleOcrAdapter

    engine = PaddleOcrAdapter(models_dir)
    try:
        engine.warm_up()
    except OcrProcessingError as exc:
        print(f"OCR engine unavailable: {exc}\n")
        return None
    return engine


def run(folder: Path, models_dir: Path, *, verbose: bool) -> int:
    images = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    if not images:
        print(f"No images found in {folder}")
        return 1

    preprocessor = OpenCvPreprocessor()
    profile = PreprocessProfile()
    qr_decoder = ZxingQrDecoder()
    recognizer = build_recognizer(models_dir)
    mrz_reader = Td1MrzReader(recognizer) if recognizer is not None else None

    counts: Counter[str] = Counter()
    attempt_wins: Counter[int] = Counter()
    elapsed = 0.0
    mrz_elapsed = 0.0

    for path in images:
        try:
            image_set = preprocessor.prepare(path.read_bytes(), None, profile)
        except OcrProcessingError as exc:
            counts["preprocess_failed"] += 1
            print(f"{path.name[:44]:46} PREPROCESS {type(exc).__name__}")
            continue

        started = time.perf_counter()
        qr = qr_decoder.decode(image_set)
        elapsed += time.perf_counter() - started

        if qr.available and qr.layout_recognized:
            counts["qr_parsed"] += 1
            attempt_wins[qr.attempts] += 1
            status = f"QR ok (attempt {qr.attempts}, {len(qr.fields)} fields)"
        elif qr.available:
            counts["qr_layout_rejected"] += 1
            status = "QR payload layout rejected"
        else:
            status = "QR not found"

        if mrz_reader is not None:
            started = time.perf_counter()
            mrz = mrz_reader.read(image_set, CCCD_CHIP)
            mrz_elapsed += time.perf_counter() - started
            status += _score_mrz(mrz, qr, counts)

            if verbose and mrz.available and not mrz.checksum_valid:
                for line in mrz.raw_lines:
                    print(f"{'':46}   {line}")

        print(f"{path.name[:44]:46} {status}")

    _report(len(images), counts, attempt_wins, elapsed, mrz_elapsed, mrz_reader is not None)
    return 0


def _score_mrz(mrz, qr, counts: Counter[str]) -> str:
    """Tally one image's MRZ outcome and return the line suffix describing it."""
    if mrz.available and mrz.checksum_valid:
        counts["mrz_checksum_ok"] += 1
        counts[f"repairs_{mrz.corrections_applied}"] += 1
        suffix = f" | MRZ ok (conf {mrz.confidence}, +{mrz.corrections_applied} fix)"
    elif mrz.available:
        counts["mrz_checksum_failed"] += 1
        suffix = " | MRZ checksum failed"
    else:
        counts["mrz_no_text"] += 1
        suffix = ""

    # ⭐ MRZ presence is the only per-image front/back label available before
    # the Golden Set, so record the overlap: it is what turns the QR count
    # into a rate.
    has_qr = qr.available and qr.layout_recognized
    counts[_side_bucket(has_qr, mrz.available)] += 1
    if has_qr and mrz.available:
        agree = qr.fields.get(FieldKey.ID_NUMBER) == mrz.fields.get(FieldKey.ID_NUMBER)
        counts["both_id_agree" if agree else "both_id_differ"] += 1
    return suffix


def _report(
    total: int,
    counts: Counter[str],
    attempt_wins: Counter[int],
    elapsed: float,
    mrz_elapsed: float,
    mrz_ran: bool,
) -> None:
    readable = total - counts["preprocess_failed"]
    print(f"\n{'=' * 62}\n{total} images | {readable} passed preprocessing")

    print("\nQR channel (§7.4.3, target >=90% of FRONT images)")
    print(f"  parsed             {counts['qr_parsed']:4}")
    print(f"  layout rejected    {counts['qr_layout_rejected']:4}")
    print(f"  wins by attempt    {dict(sorted(attempt_wins.items()))}")
    print(f"  mean time          {elapsed / max(total, 1) * 1000:.0f} ms/image")

    if mrz_ran:
        # An image with no readable MRZ is a front (or an unreadable back).
        fronts = counts["qr_only"] + counts["neither"]
        print("\n  side split by MRZ presence (proxy label, not ground truth)")
        print(f"    QR only        {counts['qr_only']:4}   <- front, QR read")
        print(f"    neither        {counts['neither']:4}   <- front with no QR, or unreadable back")
        print(f"    MRZ only       {counts['mrz_only']:4}   <- back")
        print(f"    both           {counts['both']:4}   <- image shows both sides?")
        if fronts:
            print(f"  ⭐ QR rate          {counts['qr_only'] / fronts * 100:.1f}% of {fronts} likely fronts")
        print(
            "  ⚠️  still not the KPI: fronts are inferred, not labelled. "
            "Confirm with the Golden Set."
        )

    print("\nMRZ channel (§7.4.4, target >=75% checksum valid)")
    if not mrz_ran:
        print("  SKIPPED — no IRegionRecognizer available yet (week 3 delivers it)")
        return
    attempted = counts["mrz_checksum_ok"] + counts["mrz_checksum_failed"]
    print(f"  checksum valid     {counts['mrz_checksum_ok']:4}")
    print(f"  checksum failed    {counts['mrz_checksum_failed']:4}")
    print(f"  no text in band    {counts['mrz_no_text']:4}  (fronts land here too)")
    print(f"  mean time          {mrz_elapsed / max(total, 1) * 1000:.0f} ms/image")
    repairs = {
        int(key.removeprefix("repairs_")): value
        for key, value in counts.items()
        if key.startswith("repairs_")
    }
    print(f"  repairs applied    {dict(sorted(repairs.items()))}  <- 0 means the read was clean")
    if counts["both"]:
        print(
            f"  QR/MRZ id agree    {counts['both_id_agree']}/{counts['both']}"
            f"  (differ: {counts['both_id_differ']})"
        )
    if attempted:
        rate = counts["mrz_checksum_ok"] / attempted * 100
        print(f"  ⭐ rate             {rate:.1f}% of {attempted} blocks read")


def _side_bucket(has_qr: bool, has_mrz: bool) -> str:
    if has_qr and has_mrz:
        return "both"
    if has_qr:
        return "qr_only"
    return "mrz_only" if has_mrz else "neither"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, help="Folder of CCCD images")
    parser.add_argument("--models", type=Path, default=DEFAULT_MODELS_DIR)
    parser.add_argument(
        "--verbose", action="store_true", help="print MRZ lines that failed checksum"
    )
    args = parser.parse_args()
    if not args.folder.is_dir():
        print(f"Not a folder: {args.folder}")
        return 1
    return run(args.folder, args.models, verbose=args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
