"""Unit tests for Loguru sink wiring (§10.8) and correlation-id propagation (§10.10)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from loguru import logger

from cocas.infrastructure.logging.loguru_config import (
    bind_correlation_id,
    configure_logging,
    get_correlation_id,
)


@pytest.fixture(autouse=True)
def _reset_logging(tmp_path: Path) -> None:
    """Every test gets its own log dir and a freshly configured logger."""
    configure_logging(log_dir=tmp_path, log_level="DEBUG", console=False)
    yield
    logger.remove()


class TestSinksCreated:
    def test_app_log_and_error_log_files_created(self, tmp_path: Path) -> None:
        logger.info("hello")
        logger.error("boom")
        logger.complete()
        assert (tmp_path / "app.log").exists()
        assert (tmp_path / "error.log").exists()

    def test_info_goes_to_app_log_only(self, tmp_path: Path) -> None:
        logger.info("just info")
        logger.complete()
        assert "just info" in (tmp_path / "app.log").read_text(encoding="utf-8")
        assert (tmp_path / "error.log").read_text(encoding="utf-8") == ""

    def test_error_goes_to_both_sinks(self, tmp_path: Path) -> None:
        logger.error("fatal thing")
        logger.complete()
        assert "fatal thing" in (tmp_path / "app.log").read_text(encoding="utf-8")
        assert "fatal thing" in (tmp_path / "error.log").read_text(encoding="utf-8")

    def test_app_log_lines_are_valid_json(self, tmp_path: Path) -> None:
        logger.info("structured")
        logger.complete()
        line = (tmp_path / "app.log").read_text(encoding="utf-8").strip().splitlines()[0]
        parsed = json.loads(line)
        assert parsed["record"]["message"] == "structured"


class TestCorrelationId:
    def test_bind_generates_uuid_when_none_given(self) -> None:
        cid = bind_correlation_id()
        assert get_correlation_id() == cid
        assert len(cid) == 36

    def test_bind_accepts_explicit_value(self) -> None:
        bind_correlation_id("req-123")
        assert get_correlation_id() == "req-123"

    def test_correlation_id_is_attached_to_log_records(self, tmp_path: Path) -> None:
        bind_correlation_id("req-abc")
        logger.info("tagged")
        logger.complete()
        line = (tmp_path / "app.log").read_text(encoding="utf-8").strip().splitlines()[0]
        parsed = json.loads(line)
        assert parsed["record"]["extra"]["correlation_id"] == "req-abc"


class TestPiiRedactionIsWired:
    def test_message_pii_is_masked_before_it_hits_the_file(self, tmp_path: Path) -> None:
        logger.info("CCCD 001199012345 processed")
        logger.complete()
        content = (tmp_path / "app.log").read_text(encoding="utf-8")
        assert "001199012345" not in content
        assert "••••••••2345" in content

    def test_bound_context_pii_is_masked(self, tmp_path: Path) -> None:
        logger.bind(full_name="NGUYỄN VĂN AN").info("customer created")
        logger.complete()
        content = (tmp_path / "app.log").read_text(encoding="utf-8")
        assert "NGUYỄN VĂN AN" not in content
        assert "N** V** A*" in content

    def test_exception_traceback_does_not_dump_local_variables(self, tmp_path: Path) -> None:
        """diagnose=False (§ safety note in loguru_config.py) — no variable-value dump."""
        id_number = "001199012345"  # noqa: F841 - deliberately unused, simulating a crash-site local

        def _boom() -> None:
            raise ValueError("simulated failure")

        try:
            _boom()
        except ValueError:
            logger.exception("handler failed")
        logger.complete()
        content = (tmp_path / "app.log").read_text(encoding="utf-8")
        assert "001199012345" not in content
