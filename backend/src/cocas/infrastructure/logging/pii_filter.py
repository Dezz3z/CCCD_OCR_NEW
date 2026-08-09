"""Mandatory PII redaction for logs (§10.9) — three layers of defence.

1. Regex scan of free text (`redact_text`) — catches CCCD/phone/email/bank-account/
   securities-account shaped substrings wherever they appear.
2. Sensitive-key scan of structured context (`redact_context`) — catches values that
   don't have a distinctive shape (full name, address) by looking at the *key* they
   were bound under, plus a full-redact list for secrets/tokens/raw QR-MRZ payloads.
3. The CI-mandated `grep` regression test (`tests/security/test_pii_in_logs.py`) is
   the final backstop — it scans the *whole* rendered log file, not just the fields
   this module touches, so it also catches PII embedded directly in a message string
   (see `redact_text`'s docstring for why that path is a known blind spot).

⭐ Call sites should never interpolate raw PII into a log message string — always
pass it via `logger.bind(field=value)` so `redact_context` can see the field name.
`redact_text` cannot recognize a bare name or address by shape alone; only the
digit/email patterns in the table below are recognizable without a key name.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

MASK_DOT = "•"
MASK_STAR = "*"

# §4.3-seeded 63-province list (backend/migrations/versions/20260811_005_seed_province.py),
# duplicated here on purpose: the log filter must never round-trip to the database to
# decide how to mask one line, so it carries its own small static copy for display only.
_VN_PROVINCES = (
    "Hà Nội", "Hà Giang", "Cao Bằng", "Bắc Kạn", "Tuyên Quang", "Lào Cai", "Điện Biên",
    "Lai Châu", "Sơn La", "Yên Bái", "Hòa Bình", "Thái Nguyên", "Lạng Sơn", "Quảng Ninh",
    "Bắc Giang", "Phú Thọ", "Vĩnh Phúc", "Bắc Ninh", "Hải Dương", "Hải Phòng", "Hưng Yên",
    "Thái Bình", "Hà Nam", "Nam Định", "Ninh Bình", "Thanh Hóa", "Nghệ An", "Hà Tĩnh",
    "Quảng Bình", "Quảng Trị", "Thừa Thiên Huế", "Đà Nẵng", "Quảng Nam", "Quảng Ngãi",
    "Bình Định", "Phú Yên", "Khánh Hòa", "Ninh Thuận", "Bình Thuận", "Kon Tum", "Gia Lai",
    "Đắk Lắk", "Đắk Nông", "Lâm Đồng", "Bình Phước", "Tây Ninh", "Bình Dương", "Đồng Nai",
    "Bà Rịa - Vũng Tàu", "TP. Hồ Chí Minh", "Long An", "Tiền Giang", "Bến Tre", "Trà Vinh",
    "Vĩnh Long", "Đồng Tháp", "An Giang", "Kiên Giang", "Cần Thơ", "Hậu Giang", "Sóc Trăng",
    "Bạc Liêu", "Cà Mau",
)

_CCCD_RE = re.compile(r"\b\d{12}\b")
_PHONE_RE = re.compile(r"\b0\d{9}\b")
_SECURITIES_RE = re.compile(r"\b(\d{3}C)(\d{6})\b")
_BANK_ACCOUNT_RE = re.compile(r"\b\d{9,20}\b")
_EMAIL_RE = re.compile(r"\b[\w.%+-]+@[\w.-]+\.\w+\b")

_RAW_PAYLOAD_KEY_TOKENS = ("qr_raw", "qr_payload", "mrz_raw", "mrz_text", "raw_engine_output", "raw_payload")
_SECRET_KEY_TOKENS = ("password", "token", "secret", "passphrase", "apikey", "api_key", "kek", "dek", "key")
_ADDRESS_KEY_TOKENS = ("address",)
_NAME_KEY_TOKENS = ("name",)


def _mask_suffix(match: re.Match[str], keep: int) -> str:
    value = match.group(0)
    return MASK_DOT * (len(value) - keep) + value[-keep:]


def _mask_securities(match: re.Match[str]) -> str:
    prefix, digits = match.group(1), match.group(2)
    return f"{prefix}{MASK_DOT * 3}{digits[-3:]}"


def _mask_email(match: re.Match[str]) -> str:
    local, domain = match.group(0).split("@", 1)
    domain_parts = domain.split(".")
    domain_masked = domain_parts[0][0] + MASK_STAR * 3
    if len(domain_parts) > 1:
        domain_masked += "." + ".".join(domain_parts[1:])
    return f"{local[0]}{MASK_STAR * 3}@{domain_masked}"


def redact_text(text: str) -> str:
    """Mask CCCD/phone/securities-account/bank-account/email shapes in free text.

    Order matters: CCCD (exact 12 digits) and phone (leading 0 + 9 digits) and
    securities-account (NNNCNNNNNN) are matched *before* the generic 9-20 digit
    bank-account pattern, so a CCCD or phone number is masked with its own rule
    instead of falling through to the coarser one. Each pass consumes the digits
    it masks, so a later, broader pattern can no longer re-match the same span.
    """
    text = _CCCD_RE.sub(lambda m: _mask_suffix(m, 4), text)
    text = _PHONE_RE.sub(lambda m: _mask_suffix(m, 3), text)
    text = _SECURITIES_RE.sub(_mask_securities, text)
    text = _BANK_ACCOUNT_RE.sub(lambda m: _mask_suffix(m, 4), text)
    text = _EMAIL_RE.sub(_mask_email, text)
    return text


def _mask_full_name(value: str) -> str:
    return " ".join(w[0] + MASK_STAR * min(len(w) - 1, 2) for w in value.split() if w)


def _mask_address(value: str) -> str:
    for province in _VN_PROVINCES:
        if province in value:
            return f"[địa chỉ] {province}"
    return "[REDACTED:address]"


def _redact_value_for_key(key: str, value: Any) -> Any:
    if isinstance(value, Mapping):
        return redact_context(value)
    if isinstance(value, list | tuple):
        return [_redact_value_for_key(key, item) for item in value]
    if not isinstance(value, str):
        return value

    normalized_key = key.lower()
    if any(token in normalized_key for token in _RAW_PAYLOAD_KEY_TOKENS):
        return f"[REDACTED:{key}]"
    if any(token in normalized_key for token in _SECRET_KEY_TOKENS):
        return "[REDACTED]"
    if any(token in normalized_key for token in _ADDRESS_KEY_TOKENS):
        return _mask_address(value)
    if any(token in normalized_key for token in _NAME_KEY_TOKENS):
        return _mask_full_name(value)
    return redact_text(value)


def redact_context(context: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively mask a structured `extra`/`context` mapping by key name."""
    return {key: _redact_value_for_key(key, value) for key, value in context.items()}
