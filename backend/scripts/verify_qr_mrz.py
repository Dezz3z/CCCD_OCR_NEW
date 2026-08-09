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
    zone_map={"mrz": {"x": 0.02, "y": 0.82, "w": 0.96, "h": 0.16}},
    anchor_patterns={},
    has_qr=True,
    has_mrz=True,
    is_ocr_supported=True,
    expected_aspect_ratio=1.585,
)


def build_recognizer() -> IRegionRecognizer | None:
    """Return a real region recognizer once an engine adapter exists."""
    try:
        from cocas.infrastructure.ocr.engines.paddle_adapter import (  # type: ignore[import-not-found]
            PaddleOcrAdapter,
        )
    except ImportError:
        return None
    engine = PaddleOcrAdapter()
    engine.warm_up()
    return engine


def run(folder: Path) -> int:
    images = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    if not images:
        print(f"No images found in {folder}")
        return 1

    preprocessor = OpenCvPreprocessor()
    profile = PreprocessProfile()
    qr_decoder = ZxingQrDecoder()
    recognizer = build_recognizer()
    mrz_reader = Td1MrzReader(recognizer) if recognizer is not None else None

    counts: Counter[str] = Counter()
    attempt_wins: Counter[int] = Counter()
    elapsed = 0.0

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
            mrz = mrz_reader.read(image_set, CCCD_CHIP)
            if mrz.available and mrz.checksum_valid:
                counts["mrz_checksum_ok"] += 1
                status += " | MRZ ok"
            elif mrz.available:
                counts["mrz_checksum_failed"] += 1
                status += " | MRZ checksum failed"

        print(f"{path.name[:44]:46} {status}")

    _report(len(images), counts, attempt_wins, elapsed, mrz_reader is not None)
    return 0


def _report(
    total: int,
    counts: Counter[str],
    attempt_wins: Counter[int],
    elapsed: float,
    mrz_ran: bool,
) -> None:
    readable = total - counts["preprocess_failed"]
    print(f"\n{'=' * 62}\n{total} images | {readable} passed preprocessing")

    print("\nQR channel (§7.4.3, target >=90% of FRONT images)")
    print(f"  parsed             {counts['qr_parsed']:4}")
    print(f"  layout rejected    {counts['qr_layout_rejected']:4}")
    print(f"  wins by attempt    {dict(sorted(attempt_wins.items()))}")
    print(f"  mean time          {elapsed / max(total, 1) * 1000:.0f} ms/image")
    print(
        "  ⚠️  rate not computed: the front/back label per image is unknown. "
        "Use the Golden Set to get a real denominator."
    )

    print("\nMRZ channel (§7.4.4, target >=75% checksum valid)")
    if not mrz_ran:
        print("  SKIPPED — no IRegionRecognizer available yet (week 3 delivers it)")
        return
    attempted = counts["mrz_checksum_ok"] + counts["mrz_checksum_failed"]
    print(f"  checksum valid     {counts['mrz_checksum_ok']:4}")
    print(f"  checksum failed    {counts['mrz_checksum_failed']:4}")
    if attempted:
        rate = counts["mrz_checksum_ok"] / attempted * 100
        print(f"  ⭐ rate             {rate:.1f}% of {attempted} blocks read")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, help="Folder of CCCD images")
    args = parser.parse_args()
    if not args.folder.is_dir():
        print(f"Not a folder: {args.folder}")
        return 1
    return run(args.folder)


if __name__ == "__main__":
    raise SystemExit(main())
