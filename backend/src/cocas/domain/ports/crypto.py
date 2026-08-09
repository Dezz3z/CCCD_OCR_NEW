"""Cryptography port (§12.17 `ICryptoService`) — port 18 of 18."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class AadContext:
    """Additional Authenticated Data binding a ciphertext to its exact cell.

    ⭐ AAD = `entity_id ‖ table_name ‖ column_name`. This is what stops a
    cell-swapping attack: a ciphertext lifted from another row or another
    column fails authentication instead of silently decrypting.
    """

    entity_id: str
    table_name: str
    column_name: str

    def as_bytes(self) -> bytes:
        """Canonical byte encoding used as the GCM AAD."""
        return f"{self.entity_id}|{self.table_name}|{self.column_name}".encode()


class BidxField(str, Enum):
    """Fields that carry a blind index for equality lookup on encrypted data (DB-06)."""

    ID_NUMBER = "id_number"
    PHONE = "phone"
    EMAIL = "email"
    SECURITIES_ACCOUNT = "securities_account"
    BANK_ACCOUNT_NUMBER = "bank_account_number"


@runtime_checkable
class ICryptoService(Protocol):
    """⭐ Port 18 — envelope encryption for PII at rest (§12.17).

    Implementations: `DpapiCryptoService` (production) · `NullCryptoService` (dev).

    Invariants:
      - cell format is `version(1) ‖ nonce(12) ‖ ciphertext ‖ tag(16)`;
      - ⭐ a fresh random nonce every single encryption — never reused;
      - `blind_index` is deterministic: `HMAC-SHA256(PEPPER, normalize(v))[0:16]`.

    Must never: write a key to a log, return a key through the API, or
    persist a key to disk in the clear.
    """

    def encrypt(self, plaintext: bytes, aad: AadContext) -> bytes:
        """Raises: KeyUnavailableError if the KEK has not been loaded."""
        ...

    def decrypt(self, ciphertext: bytes, aad: AadContext) -> bytes:
        """Raises:
        DecryptionError: authentication tag mismatch (tampering or wrong AAD).
        KeyUnavailableError: the KEK has not been loaded.
        """
        ...

    def blind_index(self, value: str, field: BidxField) -> bytes:
        """Deterministic 16-byte lookup token for an encrypted value."""
        ...
