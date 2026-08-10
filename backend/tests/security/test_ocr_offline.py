"""⭐ P-01 regression: the OCR engine must never reach for the network.

PaddleOCR's default behaviour is to download whatever model it cannot find, at
runtime, from Baidu's CDN — silently, and successfully, on any connected
developer machine. That is the single easiest way for this project to violate
"Offline-First" without anyone noticing, because everything keeps working.

So this test severs the socket layer and then does real work through it. It is
marked `security` alongside the PII-in-logs regression for the same reason:
both check a property that only fails in the field.

Skipped when `resources/ocr-models/` has not been populated —
`scripts/fetch_ocr_models.py` is a build step, not a test fixture.
"""
from __future__ import annotations

import socket
from pathlib import Path

import numpy as np
import pytest

from cocas.domain.ports.ocr import OcrOptions
from cocas.infrastructure.ocr.engines import PaddleOcrAdapter
from cocas.infrastructure.ocr.preprocessing.image_data import NumpyImageData

pytestmark = pytest.mark.security

MODELS_DIR = Path(__file__).resolve().parents[2] / "resources" / "ocr-models"
PADDLE_CACHE = Path.home() / ".paddleocr"


def _models_installed() -> bool:
    return all((MODELS_DIR / slot / "inference.pdmodel").is_file() for slot in ("det", "rec", "cls"))


requires_models = pytest.mark.skipif(
    not _models_installed(),
    reason="run scripts/fetch_ocr_models.py to populate resources/ocr-models",
)


@pytest.fixture
def severed_network(monkeypatch):
    """Break every way to open a connection, and record any attempt.

    ⭐ Patches the connect *methods*, never the `socket` class: `ssl.SSLSocket`
    subclasses it at import time, so replacing the class breaks the interpreter
    rather than the test.
    """
    attempts: list[object] = []

    def blocked(*args, **kwargs):
        attempts.append(args)
        raise OSError("network severed by test")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    return attempts


@requires_models
class TestEngineRunsOffline:
    def test_warm_up_needs_no_network(self, severed_network):
        engine = PaddleOcrAdapter(MODELS_DIR)
        engine.warm_up()
        assert engine.get_info().is_ready is True
        assert severed_network == []

    def test_recognition_needs_no_network(self, severed_network):
        engine = PaddleOcrAdapter(MODELS_DIR)
        engine.warm_up()
        blank = NumpyImageData(np.full((320, 512, 3), 240, np.uint8))
        assert engine.recognize(blank, OcrOptions()) == []
        assert severed_network == []

    def test_no_download_cache_is_ever_created(self, severed_network):
        """⭐ `~/.paddleocr` existing at all means a model was fetched at runtime."""
        PaddleOcrAdapter(MODELS_DIR).warm_up()
        assert not PADDLE_CACHE.exists()


class TestMissingModelsFailLoudly:
    """⭐ The other half of P-01: when models are absent the engine must refuse,
    not quietly fetch them. Runs everywhere — no installed models required."""

    def test_an_empty_model_directory_is_an_error_not_a_download(
        self, tmp_path, severed_network
    ):
        from cocas.domain.exceptions import OcrEngineUnavailableError

        with pytest.raises(OcrEngineUnavailableError):
            PaddleOcrAdapter(tmp_path).warm_up()
        assert severed_network == []
