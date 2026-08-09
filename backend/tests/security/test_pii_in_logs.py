"""⭐ Mandatory CI gate (§10.9 layer 3, CLAUDE.md: "grep PII trong log → 0 kết quả").

Runs a simulated business flow through the real, fully-wired logger, then does a
blind full-file `grep` for the exact literal PII samples named in §10.9's own
table — not just the fields `pii_filter.py` touches. A hit anywhere in either log
file — including inside an exception traceback, not just `record["message"]` —
must fail this test. This is the final backstop layer; it must never be weakened
to inspect only specific JSON fields.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from loguru import logger

from cocas.infrastructure.logging.loguru_config import bind_correlation_id, configure_logging

pytestmark = pytest.mark.security

# The exact 4 literal samples named in docs/design/10-bao-mat-va-logging.md §10.9.
_KNOWN_PII_SAMPLES = (
    "001199012345",
    "0912345678",
    "nguyenvanan@example.com",
    "008C123456",
)


def _run_sample_business_flow() -> None:
    """Stand-in for "chạy toàn bộ luồng nghiệp vụ" — logs PII the way real call
    sites are expected to: via `logger.bind(...)`, via free-text interpolation
    (the known blind spot for name/address shapes, well covered here since these
    4 samples are all shape-recognizable), and via a raised exception.
    """
    bind_correlation_id("req-security-test")

    logger.info("Customer created: id_number={}", "001199012345")
    logger.bind(
        full_name="NGUYỄN VĂN AN",
        phone="0912345678",
        email="nguyenvanan@example.com",
        securities_account_no="008C123456",
        address="123 Đường Láng, Đống Đa, Hà Nội",
    ).info("Customer profile bound to record")

    duplicate_id_number = "001199012345"
    duplicate_phone = "0912345678"
    try:
        # Realistic shape: the raw values live in variables, as in any real call
        # site — never hard-coded as literal digits in the raise statement itself.
        raise ValueError(f"Duplicate CCCD blind index for {duplicate_id_number}, phone {duplicate_phone}")
    except ValueError:
        logger.exception("Customer creation failed")

    logger.warning(
        "Bank account {} linked to securities account {}", "1234567890123", "008C123456"
    )
    logger.complete()


class TestNoPiiInLogFiles:
    def test_known_pii_samples_never_appear_in_app_log(self, tmp_path: Path) -> None:
        configure_logging(log_dir=tmp_path, log_level="DEBUG", console=False)
        try:
            _run_sample_business_flow()
        finally:
            logger.remove()

        content = (tmp_path / "app.log").read_text(encoding="utf-8")
        found = [sample for sample in _KNOWN_PII_SAMPLES if sample in content]
        assert found == [], f"PII leaked into app.log: {found}"

    def test_known_pii_samples_never_appear_in_error_log(self, tmp_path: Path) -> None:
        configure_logging(log_dir=tmp_path, log_level="DEBUG", console=False)
        try:
            _run_sample_business_flow()
        finally:
            logger.remove()

        content = (tmp_path / "error.log").read_text(encoding="utf-8")
        found = [sample for sample in _KNOWN_PII_SAMPLES if sample in content]
        assert found == [], f"PII leaked into error.log: {found}"
