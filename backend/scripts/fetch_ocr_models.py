"""Fetch the PP-OCR inference models into `resources/ocr-models/` — a BUILD step.

⭐ This script is the reason `PaddleOcrAdapter` can honour P-01. PaddleOCR
downloads missing models on first use, at runtime, from the internet. The
adapter refuses to let that happen by passing explicit `*_model_dir` paths;
this script is what puts something there, once, on a developer machine.

Run it before packaging. Never from the app.

⭐ What `lang='vi'` actually resolves to in paddleocr 2.9.1 (traced, not assumed):

| Asked for | Resolved model | Note |
|---|---|---|
| `det`, `lang='vi'` | `en_PP-OCRv3_det` | `parse_lang` maps every latin language to `det_lang='en'` |
| `rec`, `lang='vi'` | `latin_PP-OCRv3_rec` | ⭐ **PP-OCRv3, not v4** — the v4 table's `latin` entry points at a v3 URL |
| `cls` | `ch_ppocr_mobile_v2.0_cls` | language-independent |

⚠️ `latin_dict.txt` (185 chars) carries only 4 of the 42 accented Vietnamese
capitals; `vi_dict.txt` (113 chars) carries all 42 but is never selected by
`lang='vi'`. Both dictionaries are copied next to the models so the mismatch
can be measured rather than argued about.

Usage:
    python scripts/fetch_ocr_models.py [--dest resources/ocr-models] [--force]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

CDN = "https://paddleocr.bj.bcebos.com"

# ⭐ A model whose existence decides how the FULL_NAME field gets read. Probed,
# not downloaded — PaddleOCR ships a `vi_dict.txt` but no `vi` model entry, so
# whether Baidu ever published matching weights is worth one HEAD request.
VIETNAMESE_REC_PROBE = f"{CDN}/PP-OCRv3/multilingual/vi_PP-OCRv3_rec_infer.tar"


@dataclass(frozen=True)
class ModelSpec:
    """One inference model: where it comes from and where it lands."""

    slot: str
    url: str
    archive_dir: str


MODELS = (
    ModelSpec("det", f"{CDN}/PP-OCRv3/english/en_PP-OCRv3_det_infer.tar", "en_PP-OCRv3_det_infer"),
    ModelSpec(
        "rec",
        f"{CDN}/PP-OCRv3/multilingual/latin_PP-OCRv3_rec_infer.tar",
        "latin_PP-OCRv3_rec_infer",
    ),
    ModelSpec(
        "cls",
        f"{CDN}/dygraph_v2.0/ch/ch_ppocr_mobile_v2.0_cls_infer.tar",
        "ch_ppocr_mobile_v2.0_cls_infer",
    ),
)

# Character dictionaries are copied out of the installed package so the packaged
# app never reaches into site-packages at runtime.
DICTS = ("latin_dict.txt", "vi_dict.txt", "en_dict.txt")

_TIMEOUT_SECONDS = 120


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _download(url: str, destination: Path) -> str:
    """Download to a temp file, hash it, then rename — the project's file rule."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=destination.parent, suffix=".part", delete=False
    ) as staging:
        staging_path = Path(staging.name)
        with urllib.request.urlopen(url, timeout=_TIMEOUT_SECONDS) as response:
            shutil.copyfileobj(response, staging)

    checksum = _sha256(staging_path)
    staging_path.replace(destination)
    return checksum


def _extract(archive: Path, spec: ModelSpec, dest_root: Path) -> Path:
    """Unpack one model tar into `dest_root/<slot>/`, flattening its top folder."""
    slot_dir = dest_root / spec.slot
    if slot_dir.exists():
        shutil.rmtree(slot_dir)

    with tempfile.TemporaryDirectory(dir=dest_root) as staging:
        with tarfile.open(archive) as tar:
            tar.extractall(staging, filter="data")
        unpacked = Path(staging) / spec.archive_dir
        source = unpacked if unpacked.is_dir() else Path(staging)
        slot_dir.mkdir(parents=True)
        for item in source.iterdir():
            if item.is_file():
                shutil.copy2(item, slot_dir / item.name)
    return slot_dir


def _copy_dicts(dest_root: Path) -> list[str]:
    """Copy the character dictionaries out of the installed paddleocr package."""
    try:
        import paddleocr
    except ImportError:
        print("  ! paddleocr not installed — skipping dictionaries", file=sys.stderr)
        return []

    source_dir = Path(paddleocr.__file__).parent / "ppocr" / "utils" / "dict"
    target_dir = dest_root / "dict"
    target_dir.mkdir(parents=True, exist_ok=True)

    copied = []
    for name in DICTS:
        source = source_dir / name
        if source.is_file():
            shutil.copy2(source, target_dir / name)
            copied.append(name)
    return copied


def _probe(url: str) -> int | str:
    """HEAD the URL and report its status — no bytes are written."""
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return int(response.status)
    except urllib.error.HTTPError as error:
        return int(error.code)
    except OSError as error:
        return f"unreachable ({error})"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dest",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "resources" / "ocr-models",
    )
    parser.add_argument("--force", action="store_true", help="re-download even if present")
    arguments = parser.parse_args()

    dest_root: Path = arguments.dest.resolve()
    dest_root.mkdir(parents=True, exist_ok=True)
    print(f"Destination: {dest_root}\n")

    manifest: dict[str, object] = {"source": CDN, "models": {}}
    archives = dest_root / "_archives"

    for spec in MODELS:
        slot_dir = dest_root / spec.slot
        archive = archives / f"{spec.archive_dir}.tar"

        if slot_dir.is_dir() and not arguments.force:
            print(f"  = {spec.slot:4s} already present, skipping")
            continue

        print(f"  > {spec.slot:4s} {spec.url}")
        checksum = _download(spec.url, archive)
        _extract(archive, spec, dest_root)
        size_mb = archive.stat().st_size / 1e6
        print(f"    {size_mb:.1f} MB  sha256={checksum[:16]}…")
        manifest["models"][spec.slot] = {  # type: ignore[index]
            "url": spec.url,
            "sha256": checksum,
            "bytes": archive.stat().st_size,
        }

    print()
    copied = _copy_dicts(dest_root)
    print(f"  dictionaries: {', '.join(copied) if copied else 'none'}")

    if manifest["models"]:
        (dest_root / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

    print(f"\n  probing for a Vietnamese rec model…\n    {VIETNAMESE_REC_PROBE}")
    print(f"    -> {_probe(VIETNAMESE_REC_PROBE)}")

    if archives.is_dir():
        shutil.rmtree(archives)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
