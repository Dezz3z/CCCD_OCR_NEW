"""`ICryptoService` implementations (§12.17, §4.8.2).

Cell format for every encrypted column: `version(1) ‖ nonce(12) ‖
ciphertext(n) ‖ tag(16)`. `AESGCM.encrypt()` already returns
`ciphertext ‖ tag` concatenated, so the wire format is just
`version_byte + nonce + aesgcm_output`.
"""
from __future__ import annotations

import base64
import hmac
import secrets
from hashlib import sha256

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from cocas.domain.exceptions import DecryptionError, KeyUnavailableError
from cocas.domain.ports.crypto import AadContext, BidxField
from cocas.infrastructure.security.blind_index import normalize_for_blind_index

CELL_FORMAT_VERSION = b"\x01"
NONCE_LENGTH_BYTES = 12
KEK_LENGTH_BYTES = 32
BLIND_INDEX_LENGTH_BYTES = 16

_BIDX_HKDF_INFO = b"cocas-bidx-v1"
_VAULT_HKDF_INFO = b"cocas-vault-v1"


def _hkdf(kek: bytes, info: bytes) -> bytes:
    return HKDF(algorithm=SHA256(), length=32, salt=None, info=info).derive(kek)


class DpapiCryptoService:
    """⭐ Port `ICryptoService` — production implementation.

    Takes the already-unwrapped KEK (see `DpapiKeyManager`) and derives
    PEPPER/VAULT_KEY from it via HKDF — one root secret, everything else
    derived (§4.8.1: "chỉ phải bảo vệ MỘT bí mật gốc. Xoay KEK là xoay tất cả").
    """

    def __init__(self, kek: bytes) -> None:
        if len(kek) != KEK_LENGTH_BYTES:
            raise KeyUnavailableError(f"KEK phải dài đúng {KEK_LENGTH_BYTES} byte.")
        self._kek = kek
        self._aesgcm = AESGCM(kek)
        self._pepper = _hkdf(kek, _BIDX_HKDF_INFO)

    @property
    def vault_key(self) -> bytes:
        """Derived key for `EncryptedFileVault` — never used for cell encryption."""
        return _hkdf(self._kek, _VAULT_HKDF_INFO)

    def encrypt(self, plaintext: bytes, aad: AadContext) -> bytes:
        nonce = secrets.token_bytes(NONCE_LENGTH_BYTES)
        ciphertext_and_tag = self._aesgcm.encrypt(nonce, plaintext, aad.as_bytes())
        return CELL_FORMAT_VERSION + nonce + ciphertext_and_tag

    def decrypt(self, ciphertext: bytes, aad: AadContext) -> bytes:
        min_length = len(CELL_FORMAT_VERSION) + NONCE_LENGTH_BYTES
        if len(ciphertext) < min_length or ciphertext[:1] != CELL_FORMAT_VERSION:
            raise DecryptionError("Định dạng dữ liệu mã hoá không hợp lệ.")
        nonce = ciphertext[1 : 1 + NONCE_LENGTH_BYTES]
        ciphertext_and_tag = ciphertext[1 + NONCE_LENGTH_BYTES :]
        try:
            result: bytes = self._aesgcm.decrypt(nonce, ciphertext_and_tag, aad.as_bytes())
        except InvalidTag as exc:
            raise DecryptionError(
                "Giải mã thất bại — dữ liệu có thể đã bị sửa đổi hoặc sai ngữ cảnh."
            ) from exc
        return result

    def blind_index(self, value: str, field: BidxField) -> bytes:
        normalized = normalize_for_blind_index(value, field)
        # ⭐ field.value is mixed into the HMAC message (§4.8.4, fixed 2026-08-09)
        # so two different fields that happen to normalize to the same string
        # (e.g. a phone number and a bank account number both "0912345678")
        # never produce the same blind index.
        message = f"{field.value}\x00{normalized}".encode()
        digest = hmac.new(self._pepper, message, sha256).digest()
        return digest[:BLIND_INDEX_LENGTH_BYTES]


class NullCryptoService:
    """⭐ Port `ICryptoService` — dev-only stand-in.

    ⚠️ NOT ENCRYPTION. Base64-encodes so the round trip works and the byte
    format still resembles a real cell, but anyone with DB access reads the
    data trivially. Selected only via an explicit dev/local setting — never
    the production default (see Composition Root wiring, task #12).
    """

    def encrypt(self, plaintext: bytes, aad: AadContext) -> bytes:
        return CELL_FORMAT_VERSION + aad.as_bytes() + b"\x00" + base64.b64encode(plaintext)

    def decrypt(self, ciphertext: bytes, aad: AadContext) -> bytes:
        prefix = CELL_FORMAT_VERSION + aad.as_bytes() + b"\x00"
        if not ciphertext.startswith(prefix):
            raise DecryptionError("Giải mã thất bại — sai ngữ cảnh (AAD).")
        return base64.b64decode(ciphertext[len(prefix) :])

    def blind_index(self, value: str, field: BidxField) -> bytes:
        normalized = normalize_for_blind_index(value, field)
        message = f"{field.value}\x00{normalized}".encode()
        digest = hmac.new(b"null-crypto-service-dev-only", message, sha256)
        return digest.digest()[:BLIND_INDEX_LENGTH_BYTES]
