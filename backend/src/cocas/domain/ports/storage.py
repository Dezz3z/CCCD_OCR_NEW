"""File-vault port (§12.13 `EncryptedFileVault`) — port 11 of 18."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable


class VaultCategory(str, Enum):
    """Top-level partition of the Vault, and the first path segment."""

    CARD_IMAGE = "card_image"
    THUMBNAIL = "thumbnail"
    CONTRACT_DOCUMENT = "contract_document"
    TEMPLATE = "template"


@dataclass(frozen=True, slots=True)
class VaultRef:
    """A handle to a stored file.

    ⭐ `relative_path` is ALWAYS relative to the Vault root and always has the
    shape `{category}/{yyyy}/{mm}/{dd}/{uuid}.enc` — the filename is a UUID,
    never anything the user controls (§12.13).
    """

    category: VaultCategory
    relative_path: str


@runtime_checkable
class IFileStorage(Protocol):
    """⭐ Port 11 — encrypted file storage.

    Implementations: `EncryptedFileVault` (production) · `InMemoryFileStorage`
    (tests). ⭐ There is deliberately **no** `PlainFileVault`: the Container
    has no dev mode (§12.13.3), the same decision already taken in P1 for
    `NullCryptoService`.

    Invariants every implementation must uphold:
      - writes follow write-temp → verify → rename, so a partially written
        file never exists at the destination path;
      - `load()` resolves the path and verifies it stays inside the Vault
        root, raising `PathTraversalError` otherwise;
      - absolute paths are never accepted as input nor returned as output.
    """

    def save(self, data: bytes, category: VaultCategory) -> VaultRef:
        """Store `data` and return its reference.

        Raises:
            InsufficientStorageError: not enough free disk space.
        """
        ...

    def load(self, ref: VaultRef) -> bytes:
        """Read a stored file back.

        Raises:
            PathTraversalError: the resolved path escaped the Vault root.
            VaultFileNotFoundError: no such file.
            DecryptionError: the stored bytes failed authentication.
        """
        ...

    def delete(self, ref: VaultRef) -> None:
        """Remove a stored file. Idempotent — deleting a missing file is not an error."""
        ...

    def exists(self, ref: VaultRef) -> bool: ...
