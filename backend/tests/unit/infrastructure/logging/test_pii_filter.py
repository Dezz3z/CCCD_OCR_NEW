"""Unit tests for the log PII redaction filter (§10.9)."""
from __future__ import annotations

from cocas.infrastructure.logging.pii_filter import redact_context, redact_text


class TestRedactTextShapes:
    def test_cccd_number(self) -> None:
        assert redact_text("id_number=001199012345") == "id_number=••••••••2345"

    def test_phone_number(self) -> None:
        assert redact_text("call 0912345678 now") == "call •••••••678 now"

    def test_bank_account_number(self) -> None:
        assert redact_text("acct 1234567890123") == "acct •••••••••0123"

    def test_securities_account_number(self) -> None:
        assert redact_text("sec 008C123456") == "sec 008C•••456"

    def test_email(self) -> None:
        assert redact_text("mail an@example.com") == "mail a***@e***.com"

    def test_email_multi_label_domain(self) -> None:
        assert redact_text("mail an@mail.example.com") == "mail a***@m***.example.com"

    def test_no_pii_left_untouched(self) -> None:
        assert redact_text("OCR completed in 42ms") == "OCR completed in 42ms"

    def test_short_number_not_masked(self) -> None:
        """A 6-digit code (e.g. a document_type id) is below every threshold — left alone."""
        assert redact_text("code=123456") == "code=123456"

    def test_cccd_not_double_masked_as_bank_account(self) -> None:
        result = redact_text("001199012345")
        assert result == "••••••••2345"
        assert result.count("•") == 8


class TestRedactContextByKey:
    def test_full_name_key_masked_to_initials(self) -> None:
        out = redact_context({"full_name": "NGUYỄN VĂN AN"})
        assert out["full_name"] == "N** V** A*"

    def test_address_key_keeps_only_province(self) -> None:
        out = redact_context({"address": "123 Đường Láng, Đống Đa, Hà Nội"})
        assert out["address"] == "[địa chỉ] Hà Nội"

    def test_address_key_without_recognizable_province_fully_redacted(self) -> None:
        out = redact_context({"address": "somewhere unlisted"})
        assert out["address"] == "[REDACTED:address]"

    def test_password_key_fully_redacted(self) -> None:
        assert redact_context({"password": "hunter2"})["password"] == "[REDACTED]"

    def test_token_like_keys_fully_redacted(self) -> None:
        ctx = redact_context({"api_key": "abc", "access_token": "xyz", "kek": "raw-bytes"})
        assert ctx == {"api_key": "[REDACTED]", "access_token": "[REDACTED]", "kek": "[REDACTED]"}

    def test_raw_qr_payload_key_fully_redacted(self) -> None:
        out = redact_context({"qr_raw": "001199012345|NGUYEN VAN AN|..."})
        assert out["qr_raw"] == "[REDACTED:qr_raw]"

    def test_unrecognized_key_still_goes_through_shape_based_redaction(self) -> None:
        out = redact_context({"detail": "phone is 0912345678"})
        assert out["detail"] == "phone is •••••••678"

    def test_nested_dict_recurses(self) -> None:
        out = redact_context({"customer": {"full_name": "TRẦN THỊ B", "id_number": "001199012345"}})
        assert out["customer"]["full_name"] == "T** T** B"
        assert out["customer"]["id_number"] == "••••••••2345"

    def test_list_of_strings_recurses(self) -> None:
        out = redact_context({"phones": ["0912345678", "0987654321"]})
        assert out["phones"] == ["•••••••678", "•••••••321"]

    def test_non_string_scalars_left_alone(self) -> None:
        out = redact_context({"count": 3, "active": True, "ratio": 0.5, "missing": None})
        assert out == {"count": 3, "active": True, "ratio": 0.5, "missing": None}
