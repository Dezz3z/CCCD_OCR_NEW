"""Tests for DpapiCryptoService / NullCryptoService (§12.17, §4.8.2).

Pure AES-256-GCM logic only — no real DPAPI needed here (a fake 32-byte KEK
stands in). Real DPAPI wrap/unwrap is covered separately in test_dpapi.py.
"""
from __future__ import annotations

import secrets

import pytest

from cocas.domain.exceptions import DecryptionError, KeyUnavailableError
from cocas.domain.ports.crypto import AadContext, BidxField
from cocas.infrastructure.security.crypto import (
    CELL_FORMAT_VERSION,
    NONCE_LENGTH_BYTES,
    DpapiCryptoService,
    NullCryptoService,
)

FAKE_KEK = secrets.token_bytes(32)
AAD = AadContext(entity_id="cust-1", table_name="customer", column_name="id_number_enc")


class TestConstruction:
    def test_valid_kek_length(self) -> None:
        DpapiCryptoService(FAKE_KEK)

    def test_wrong_kek_length_rejected(self) -> None:
        with pytest.raises(KeyUnavailableError):
            DpapiCryptoService(secrets.token_bytes(16))


class TestRoundTrip:
    def test_encrypt_then_decrypt(self) -> None:
        crypto = DpapiCryptoService(FAKE_KEK)
        ciphertext = crypto.encrypt(b"001199012345", AAD)
        assert crypto.decrypt(ciphertext, AAD) == b"001199012345"

    def test_empty_plaintext_round_trips(self) -> None:
        crypto = DpapiCryptoService(FAKE_KEK)
        ciphertext = crypto.encrypt(b"", AAD)
        assert crypto.decrypt(ciphertext, AAD) == b""

    def test_cell_format_starts_with_version_byte(self) -> None:
        crypto = DpapiCryptoService(FAKE_KEK)
        ciphertext = crypto.encrypt(b"x", AAD)
        assert ciphertext[:1] == CELL_FORMAT_VERSION

    def test_cell_contains_12_byte_nonce_after_version(self) -> None:
        crypto = DpapiCryptoService(FAKE_KEK)
        ciphertext = crypto.encrypt(b"x", AAD)
        # version(1) + nonce(12) + ciphertext(1) + tag(16) = 30 for 1-byte plaintext
        assert len(ciphertext) == 1 + NONCE_LENGTH_BYTES + 1 + 16


class TestNonceUniqueness:
    def test_same_plaintext_yields_different_ciphertext(self) -> None:
        """⭐ §12.17: a fresh random nonce every single encryption — never reused."""
        crypto = DpapiCryptoService(FAKE_KEK)
        first = crypto.encrypt(b"same value", AAD)
        second = crypto.encrypt(b"same value", AAD)
        assert first != second

    def test_nonces_extracted_are_distinct_across_many_calls(self) -> None:
        crypto = DpapiCryptoService(FAKE_KEK)
        nonces = {crypto.encrypt(b"x", AAD)[1 : 1 + NONCE_LENGTH_BYTES] for _ in range(200)}
        assert len(nonces) == 200


class TestAadCellPermutationDefense:
    """⭐ §12.17 / §4.8.2: AAD binds ciphertext to entity+table+column — a
    cell copied to another row/column must fail to decrypt.
    """

    def test_wrong_entity_id_fails(self) -> None:
        crypto = DpapiCryptoService(FAKE_KEK)
        ciphertext = crypto.encrypt(b"secret", AAD)
        wrong_aad = AadContext(entity_id="cust-2", table_name="customer", column_name="id_number_enc")
        with pytest.raises(DecryptionError):
            crypto.decrypt(ciphertext, wrong_aad)

    def test_wrong_column_name_fails(self) -> None:
        crypto = DpapiCryptoService(FAKE_KEK)
        ciphertext = crypto.encrypt(b"secret", AAD)
        wrong_aad = AadContext(entity_id="cust-1", table_name="customer", column_name="phone_enc")
        with pytest.raises(DecryptionError):
            crypto.decrypt(ciphertext, wrong_aad)

    def test_wrong_table_name_fails(self) -> None:
        crypto = DpapiCryptoService(FAKE_KEK)
        ciphertext = crypto.encrypt(b"secret", AAD)
        wrong_aad = AadContext(entity_id="cust-1", table_name="bank_account", column_name="id_number_enc")
        with pytest.raises(DecryptionError):
            crypto.decrypt(ciphertext, wrong_aad)

    def test_cell_copied_to_different_entity_row_fails(self) -> None:
        """Simulates literally copying person A's ciphertext into person B's row."""
        crypto = DpapiCryptoService(FAKE_KEK)
        person_a_aad = AadContext(entity_id="person-a", table_name="customer", column_name="id_number_enc")
        person_b_aad = AadContext(entity_id="person-b", table_name="customer", column_name="id_number_enc")
        stolen_ciphertext = crypto.encrypt(b"001199012345", person_a_aad)
        with pytest.raises(DecryptionError):
            crypto.decrypt(stolen_ciphertext, person_b_aad)


class TestTamperDetection:
    def test_flipped_byte_in_ciphertext_fails(self) -> None:
        crypto = DpapiCryptoService(FAKE_KEK)
        ciphertext = bytearray(crypto.encrypt(b"tamper me", AAD))
        ciphertext[-1] ^= 0xFF
        with pytest.raises(DecryptionError):
            crypto.decrypt(bytes(ciphertext), AAD)

    def test_truncated_ciphertext_fails(self) -> None:
        crypto = DpapiCryptoService(FAKE_KEK)
        ciphertext = crypto.encrypt(b"tamper me", AAD)
        with pytest.raises(DecryptionError):
            crypto.decrypt(ciphertext[:5], AAD)

    def test_wrong_version_byte_fails(self) -> None:
        crypto = DpapiCryptoService(FAKE_KEK)
        ciphertext = crypto.encrypt(b"x", AAD)
        corrupted = b"\x02" + ciphertext[1:]
        with pytest.raises(DecryptionError):
            crypto.decrypt(corrupted, AAD)

    def test_wrong_kek_fails(self) -> None:
        crypto_a = DpapiCryptoService(FAKE_KEK)
        crypto_b = DpapiCryptoService(secrets.token_bytes(32))
        ciphertext = crypto_a.encrypt(b"x", AAD)
        with pytest.raises(DecryptionError):
            crypto_b.decrypt(ciphertext, AAD)


class TestBlindIndex:
    def test_deterministic(self) -> None:
        crypto = DpapiCryptoService(FAKE_KEK)
        first = crypto.blind_index("0912345678", BidxField.PHONE)
        second = crypto.blind_index("0912345678", BidxField.PHONE)
        assert first == second

    def test_length_is_16_bytes(self) -> None:
        crypto = DpapiCryptoService(FAKE_KEK)
        assert len(crypto.blind_index("test@example.com", BidxField.EMAIL)) == 16

    def test_different_field_yields_different_index(self) -> None:
        """Same underlying digits, different field -> different index (no cross-field collision)."""
        crypto = DpapiCryptoService(FAKE_KEK)
        as_phone = crypto.blind_index("0912345678", BidxField.PHONE)
        as_bank = crypto.blind_index("0912345678", BidxField.BANK_ACCOUNT_NUMBER)
        assert as_phone != as_bank

    def test_normalizes_before_hashing(self) -> None:
        """§4.8.4: phone normalization strips +84/spaces before hashing."""
        crypto = DpapiCryptoService(FAKE_KEK)
        assert crypto.blind_index("+84912345678", BidxField.PHONE) == crypto.blind_index(
            "0912345678", BidxField.PHONE
        )

    def test_different_kek_yields_different_index(self) -> None:
        """PEPPER is derived from KEK — rotating KEK changes every blind index too."""
        crypto_a = DpapiCryptoService(FAKE_KEK)
        crypto_b = DpapiCryptoService(secrets.token_bytes(32))
        assert crypto_a.blind_index("0912345678", BidxField.PHONE) != crypto_b.blind_index(
            "0912345678", BidxField.PHONE
        )

    def test_cannot_recover_value_without_pepper(self) -> None:
        """Not a cryptographic proof, just confirms the index isn't the plaintext/a trivial hash."""
        crypto = DpapiCryptoService(FAKE_KEK)
        index = crypto.blind_index("0912345678", BidxField.PHONE)
        assert b"0912345678" not in index


class TestVaultKeyDerivation:
    def test_vault_key_differs_from_kek(self) -> None:
        crypto = DpapiCryptoService(FAKE_KEK)
        assert crypto.vault_key != FAKE_KEK

    def test_vault_key_is_32_bytes(self) -> None:
        crypto = DpapiCryptoService(FAKE_KEK)
        assert len(crypto.vault_key) == 32

    def test_vault_key_deterministic_from_same_kek(self) -> None:
        assert DpapiCryptoService(FAKE_KEK).vault_key == DpapiCryptoService(FAKE_KEK).vault_key

    def test_vault_key_differs_from_pepper_derived_blind_index_material(self) -> None:
        """HKDF info strings differ ("cocas-vault-v1" vs "cocas-bidx-v1") -> independent outputs."""
        crypto = DpapiCryptoService(FAKE_KEK)
        # blind_index uses PEPPER internally; vault_key must not equal it even
        # though both derive from the same KEK.
        pepper_probe = crypto.blind_index("probe@example.com", BidxField.EMAIL)
        assert crypto.vault_key[:16] != pepper_probe


class TestNullCryptoService:
    """Dev-only stand-in — still must satisfy AAD binding + round trip."""

    def test_round_trip(self) -> None:
        crypto = NullCryptoService()
        ciphertext = crypto.encrypt(b"plaintext", AAD)
        assert crypto.decrypt(ciphertext, AAD) == b"plaintext"

    def test_wrong_aad_fails(self) -> None:
        crypto = NullCryptoService()
        ciphertext = crypto.encrypt(b"plaintext", AAD)
        wrong_aad = AadContext(entity_id="other", table_name="customer", column_name="id_number_enc")
        with pytest.raises(DecryptionError):
            crypto.decrypt(ciphertext, wrong_aad)

    def test_blind_index_deterministic(self) -> None:
        crypto = NullCryptoService()
        assert crypto.blind_index("a@b.com", BidxField.EMAIL) == crypto.blind_index(
            "a@b.com", BidxField.EMAIL
        )

    def test_is_not_real_encryption_data_recoverable(self) -> None:
        """⚠️ Documents the intentional weakness — plaintext is trivially recoverable."""
        import base64

        crypto = NullCryptoService()
        ciphertext = crypto.encrypt(b"0912345678", AAD)
        payload = ciphertext.split(b"\x00", 1)[1]
        assert base64.b64decode(payload) == b"0912345678"
