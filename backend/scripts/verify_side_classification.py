"""Measure `HeuristicSideClassifier` per card generation — the P2w3b open item.

    python scripts/verify_side_classification.py "C:/path/to/images"

⭐ Why this exists: §7.4.7 closes with a *prediction*, not a result — a Căn cước
2024 back carries **both** a QR (votes FRONT 0.40) and an MRZ (votes BACK 0.40),
so the two decisive signals should cancel and leave every 2024 pair `AMBIGUOUS`.
Week 3 measured 36/36 on the sample as a whole and never split it by generation,
which is exactly the denominator trap that hid the second generation for three
weeks. This script splits it.

Truth labels come from the card itself, never from the classifier:

  * **side** — an MRZ block that reads is a back, on *both* generations (§7.4.7
    lists the MRZ as the one thing the redesign left alone);
  * **generation** — the marker phrases in `verify_qr_mrz`, reused as-is.

Both are the same labels `verify_qr_mrz.py` reports, so the two scripts cannot
disagree about what the sample contains.
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from verify_qr_mrz import (
    CCCD_CHIP,
    DEFAULT_MODELS_DIR,
    IMAGE_SUFFIXES,
    _generation_of,
    build_recognizer,
    has_qr,
)

from cocas.domain.exceptions import OcrProcessingError
from cocas.domain.ports.ocr import PreprocessProfile, SideVerdict
from cocas.infrastructure.ocr.channels.mrz_reader import Td1MrzReader
from cocas.infrastructure.ocr.channels.qr_decoder import ZxingQrDecoder
from cocas.infrastructure.ocr.classification.side_classifier import (
    HeuristicSideClassifier,
)
from cocas.infrastructure.ocr.preprocessing.opencv_preprocessor import (
    OpenCvPreprocessor,
)

# Pairing every 2021 front with every 2021 back is 380 classifications at ~2 s
# each. The control only has to show the generation split is the variable, so
# it pairs them off one-to-one instead.
MAX_PAIRS_PER_GENERATION = 12


def run(folder: Path, models_dir: Path) -> int:
    images = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    if not images:
        print(f"No images found in {folder}")
        return 1

    recognizer = build_recognizer(models_dir)
    if recognizer is None:
        print("Cannot label generations without an engine — run fetch_ocr_models.py first.")
        return 1

    preprocessor = OpenCvPreprocessor()
    profile = PreprocessProfile()
    qr_decoder = ZxingQrDecoder()
    mrz_reader = Td1MrzReader(recognizer)
    classifier = HeuristicSideClassifier(qr_decoder, recognizer)

    # ---- pass 1: label every image, keeping paths rather than pixel buffers ----
    labelled: dict[tuple[str, str], list[Path]] = {}
    for path in images:
        try:
            image_set = preprocessor.prepare(path.read_bytes(), None, profile)
        except OcrProcessingError as exc:
            print(f"{path.name[:44]:46} PREPROCESS {type(exc).__name__}")
            continue
        qr = qr_decoder.decode(image_set)
        mrz = mrz_reader.read(image_set, CCCD_CHIP)
        side = "BACK" if mrz.available else "FRONT"
        generation = _generation_of(recognizer, image_set, side, has_qr(qr))
        labelled.setdefault((generation, side), []).append(path)
        print(f"{path.name[:44]:46} {generation}-{side}")

    print(f"\n{'=' * 62}\nsample composition")
    for key in sorted(labelled):
        print(f"  {key[0]:5} {key[1]:5} {len(labelled[key]):3}")

    # ---- pass 2: classify real (front, back) pairs, generation by generation ----
    for generation in ("2021", "2024"):
        fronts = labelled.get((generation, "FRONT"), [])
        backs = labelled.get((generation, "BACK"), [])
        if not fronts or not backs:
            print(f"\n{generation}: no front/back pair available — skipped")
            continue
        pairs = _pairs(fronts, backs)
        print(f"\n{generation}: {len(pairs)} pairs")
        _measure(classifier, preprocessor, profile, pairs, generation)

    return 0


def _pairs(fronts: list[Path], backs: list[Path]) -> list[tuple[Path, Path]]:
    """Every front-back combination, or a one-to-one sample when that explodes."""
    combinations = [(f, b) for f in fronts for b in backs]
    if len(combinations) <= MAX_PAIRS_PER_GENERATION:
        return combinations
    return list(zip(fronts, backs, strict=False))[:MAX_PAIRS_PER_GENERATION]


def _measure(
    classifier: HeuristicSideClassifier,
    preprocessor: OpenCvPreprocessor,
    profile: PreprocessProfile,
    pairs: list[tuple[Path, Path]],
    generation: str,
) -> None:
    verdicts: Counter[str] = Counter()
    correct = 0
    wrong = 0
    elapsed = 0.0

    for front_path, back_path in pairs:
        front_set = preprocessor.prepare(front_path.read_bytes(), None, profile)
        back_set = preprocessor.prepare(back_path.read_bytes(), None, profile)

        # ⭐ Feed them in the WRONG order on purpose: image A is the back. A
        # classifier that quietly defaults to "A is the front" scores 100% on
        # correctly-ordered input and 0% here, and the wrong order is the case
        # ALT-01 exists for.
        started = time.perf_counter()
        result = classifier.classify(back_set, front_set, CCCD_CHIP)
        elapsed += time.perf_counter() - started

        verdicts[result.verdict.value] += 1
        if result.verdict is SideVerdict.RESOLVED:
            if result.front_index == 1:
                correct += 1
                mark = "ok"
            else:
                wrong += 1
                mark = "WRONG"
        else:
            mark = "—"
        print(
            f"  {front_path.name[:22]:24} + {back_path.name[:22]:24} "
            f"{result.verdict.value:14} conf {result.confidence_a:.2f}/"
            f"{result.confidence_b:.2f}  {mark}"
        )

    total = len(pairs)
    print(f"  verdicts           {dict(verdicts)}")
    print(f"  resolved correctly {correct}/{total}   wrong {wrong}")
    print(f"  mean time          {elapsed / max(total, 1) * 1000:.0f} ms/pair")
    if wrong:
        print(f"  ⚠️  {generation}: a WRONG verdict is worse than AMBIGUOUS — it swaps "
              "both sides silently")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, help="Folder of CCCD images")
    parser.add_argument("--models", type=Path, default=DEFAULT_MODELS_DIR)
    args = parser.parse_args()
    if not args.folder.is_dir():
        print(f"Not a folder: {args.folder}")
        return 1
    return run(args.folder, args.models)


if __name__ == "__main__":
    raise SystemExit(main())
