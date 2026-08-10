"""OCR engine adapters — Ports 1 & 2, plus the engine-backed orientation vote."""
from .orientation_oracle import PaddleOrientationOracle
from .paddle_ocr_adapter import PaddleOcrAdapter

__all__ = ["PaddleOcrAdapter", "PaddleOrientationOracle"]
