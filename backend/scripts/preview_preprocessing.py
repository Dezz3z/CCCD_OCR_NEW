"""Chạy `OpenCvPreprocessor` trên ảnh CCCD thật và ghi ra 5 biến thể để soi bằng mắt.

Đây là cách nghiệm thu tiêu chí P2 tuần 1 (roadmap §14.3): ảnh nghiêng / tối /
loá / xoay 180° phải cho ra ảnh chuẩn hoá **tốt hơn ảnh gốc**. Test đơn vị dùng
ảnh tổng hợp để khẳng định hành vi; script này dùng ảnh thật để đánh giá chất
lượng — hai việc khác nhau, không thay thế nhau được.

Cách chạy (từ thư mục `backend/`):

    python scripts/preview_preprocessing.py "C:\\Users\\me\\Downloads\\CCCD" --out .preview

Mỗi ảnh đầu vào sinh ra `<tên>_v0.jpg` … `<tên>_v4.jpg` cùng một dòng tóm tắt
(kích thước, `warp_succeeded`, điểm chất lượng, cờ, thời gian dựng từng biến thể).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2

from cocas.domain.exceptions import OcrProcessingError
from cocas.domain.ports.ocr import PreprocessProfile
from cocas.infrastructure.ocr.preprocessing import OpenCvPreprocessor

SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VARIANTS = ("v0", "v1", "v2", "v3", "v4")


def preview_one(path: Path, out_dir: Path, preprocessor: OpenCvPreprocessor) -> str:
    image_set = preprocessor.prepare(path.read_bytes(), None, PreprocessProfile())

    timings = []
    for name in VARIANTS:
        started = time.perf_counter()
        variant = getattr(image_set, name)
        timings.append(f"{name}={(time.perf_counter() - started) * 1000:.0f}ms")
        cv2.imwrite(str(out_dir / f"{path.stem}_{name}.jpg"), variant.array)

    quality = image_set.quality
    flags = ",".join(quality.flags) or "-"
    return (
        f"{path.name:<48} {image_set.v0.width}x{image_set.v0.height}"
        f" -> v2 {image_set.v2.width}x{image_set.v2.height}"
        f" | warp={'YES' if image_set.warp_succeeded else 'no '}"
        f" | quality={quality.score:.2f} [{flags}]"
        f" | {' '.join(timings)}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Thư mục hoặc file ảnh CCCD")
    parser.add_argument("--out", type=Path, default=Path(".preview"), help="Thư mục kết quả")
    arguments = parser.parse_args()

    paths = (
        sorted(p for p in arguments.source.iterdir() if p.suffix.lower() in SUFFIXES)
        if arguments.source.is_dir()
        else [arguments.source]
    )
    if not paths:
        print(f"Không tìm thấy ảnh nào trong {arguments.source}")
        return 1

    arguments.out.mkdir(parents=True, exist_ok=True)
    preprocessor = OpenCvPreprocessor()
    failures = 0
    for path in paths:
        try:
            print(preview_one(path, arguments.out, preprocessor))
        except OcrProcessingError as error:
            failures += 1
            print(f"{path.name:<48} BỎ QUA — {error.code}: {error.message}")

    print(f"\n{len(paths) - failures}/{len(paths)} ảnh xử lý được. Kết quả: {arguments.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
