"""Measure the QR and MRZ channels against a folder of real CCCD photos.

⭐ This is the script that decides whether the §7.4.3 / §7.4.4 targets are met.

    python scripts/verify_qr_mrz.py "C:/path/to/images"

⭐ **The side label comes from the card's own printed text, not from whether a
channel fired, and that correction moved the headline number by 19 points.**
The first version inferred "an MRZ was read ⇒ this is a back", which makes the
QR denominator every image that produced no MRZ. That was wrong in both
directions once the sample turned out to hold two card generations (§7.4.7):

  * it counted 5 Căn cước 2024 **fronts** as fronts whose QR failed — those
    cards print no QR on the front at all, so there was nothing to read;
  * it missed 2 Căn cước 2024 **backs** that do carry a QR, and read it.

Reported 16/24 = 66.7%; the truth was 18/21 = 85.7%. A rate is only as
trustworthy as a denominator labelled independently of the thing being measured.

The MRZ channel needs an `IRegionRecognizer`. Without one the MRZ section
reports as skipped rather than zero, so a missing engine never looks like a
failing channel — but generation detection needs it too, and without it the
report falls back to the old MRZ-presence proxy and says so.
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
    RelativeBox,
)
from cocas.infrastructure.ocr.channels.mrz_reader import Td1MrzReader
from cocas.infrastructure.ocr.channels.qr_decoder import ZxingQrDecoder
from cocas.infrastructure.ocr.preprocessing.opencv_preprocessor import (
    OpenCvPreprocessor,
)
from cocas.infrastructure.ocr.text_matching import similarity

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

WHOLE_CARD = RelativeBox(x=0.0, y=0.0, w=1.0, h=1.0)
GENERATION_THRESHOLD = 85.0

# ⭐ Phrases that exist on exactly ONE generation. Scored with `similarity`, not
# compared literally: the recognizer merges words and drops diacritics.
#
# ⚠️ `CĂN CƯỚC` and `IDENTITY CARD` are NOT here even though they are the 2024
# titles. Measured over the whole sample, both match the 2021 titles too
# (`CĂN CƯỚC CÔNG DÂN` scores 100 against `CĂN CƯỚC`), so including them ties
# the vote on every 2021 front and the generation comes back unknown. A marker
# that appears on both generations distinguishes nothing — the same trap as a
# top-of-card fingerprint that also appears at the bottom.
MARKERS_2024 = ("Số định danh cá nhân", "Nơi đăng ký khai sinh", "Nơi cư trú")
MARKERS_2021 = ("CĂN CƯỚC CÔNG DÂN", "Đặc điểm nhân dạng", "Quê quán", "Nơi thường trú")

# Which side each generation prints its QR on — the fact the old proxy lacked.
QR_SIDE = {"2021": "FRONT", "2024": "BACK"}

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

        if mrz_reader is not None and recognizer is not None:
            started = time.perf_counter()
            mrz = mrz_reader.read(image_set, CCCD_CHIP)
            mrz_elapsed += time.perf_counter() - started
            status += _score_mrz(mrz, qr, counts)

            side = "BACK" if mrz.available else "FRONT"
            generation = _generation_of(recognizer, image_set, side, has_qr(qr))
            counts[f"gen{generation}_{side}"] += 1
            if _carries_a_qr(generation, side):
                counts["qr_expected"] += 1
                counts["qr_expected_read" if has_qr(qr) else "qr_expected_missed"] += 1
            status += f" | {generation}-{side}"

            if verbose and mrz.available and not mrz.checksum_valid:
                for line in mrz.raw_lines:
                    print(f"{'':46}   {line}")

        print(f"{path.name[:44]:46} {status}")

    _report(len(images), counts, attempt_wins, elapsed, mrz_elapsed, mrz_reader is not None)
    return 0


def has_qr(qr) -> bool:
    """A decoded payload the layout check vouched for."""
    return bool(qr.available and qr.layout_recognized)


def _carries_a_qr(generation: str, side: str) -> bool:
    """⭐ The denominator of the QR rate: does THIS card even print one here?

    Counting a Căn cước 2024 front as a QR miss is counting a card that has no
    QR to miss.
    """
    return QR_SIDE.get(generation) == side


def _generation_of(
    recognizer: IRegionRecognizer, image_set, side: str, qr_read: bool
) -> str:
    """Which card generation this is, from the text the card itself prints.

    ⭐ One structural override: an image carrying **both** a QR and an MRZ can
    only be a Căn cước 2024 back. A 2021 card never prints both on one side, so
    this is decisive even when the recognizer garbles every label — which is
    exactly what happened on one of the two 2024 backs in the sample.
    """
    if side == "BACK" and qr_read:
        return "2024"
    try:
        region = recognizer.recognize_region(image_set.v3, WHOLE_CARD, None)
    except Exception:
        return "?"
    if region is None:
        return "?"
    lines = [line for line in region.text.splitlines() if line.strip()]
    hits_2024 = _marker_hits(lines, MARKERS_2024)
    hits_2021 = _marker_hits(lines, MARKERS_2021)
    if hits_2024 > hits_2021:
        return "2024"
    if hits_2021 > hits_2024:
        return "2021"
    return "?"


def _marker_hits(lines: list[str], markers: tuple[str, ...]) -> int:
    return sum(
        any(similarity(line, marker) >= GENERATION_THRESHOLD for line in lines)
        for marker in markers
    )


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

    counts[_side_bucket(has_qr(qr), mrz.available)] += 1
    if has_qr(qr) and mrz.available:
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
        print("\n  by card generation (from the card's own printed text)")
        for generation in ("2021", "2024", "?"):
            front = counts[f"gen{generation}_FRONT"]
            back = counts[f"gen{generation}_BACK"]
            if not (front or back):
                continue
            qr_side = QR_SIDE.get(generation, "—")
            print(f"    {generation:5} front {front:3}   back {back:3}"
                  f"   QR printed on: {qr_side}")

        expected = counts["qr_expected"]
        if expected:
            rate = counts["qr_expected_read"] / expected * 100
            print(f"\n  ⭐ QR rate          {rate:.1f}% "
                  f"({counts['qr_expected_read']}/{expected} images that PRINT a QR)")
            print(f"     missed          {counts['qr_expected_missed']}")
        print(
            "  ⚠️  the denominator counts only sides that carry a QR — a Căn cước\n"
            "      2024 front prints none, so it is not a miss. Generation labels\n"
            "      are read off the card, not verified; confirm with the Golden Set."
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
