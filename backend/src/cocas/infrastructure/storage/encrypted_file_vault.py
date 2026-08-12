"""`EncryptedFileVault` — ⭐ Port 11 `IFileStorage` (§12.13).

Every byte the system stores outside PostgreSQL lands here encrypted: card
images, thumbnails, contract documents and template files (§4.8.3, "toàn bộ
file trong Vault").

## ⭐ It takes VAULT_KEY, not `ICryptoService`

Handing it the crypto service would be the obvious move — it already has
`encrypt`/`decrypt` with AAD and is already in the Container. It is also
wrong. §4.8.1's key tree has three branches off the KEK, and cell encryption
is a *different* one from the Vault:

    KEK ─┬─ HKDF("cocas-bidx-v1")  -> PEPPER      (blind index)
         ├─ HKDF("cocas-vault-v1") -> VAULT_KEY   <- this class
         └─ used directly           -> PII column cells

`ICryptoService.encrypt()` is that third branch. Calling it from here would
encrypt every image and every contract under the same key as the PII columns,
erasing exactly the separation the key tree exists to create — and no single
line of code would look wrong.

## ⭐ AAD is the Vault-relative path

Not the UUID: the path carries the category and the date too, so a `.enc`
copied from `card_image/…` into `contract_document/…` fails authentication
instead of decrypting into the wrong slot. Same defence as `ocr_field`'s
row-bound AAD (§12.17), applied to the filesystem.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import shutil
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from loguru import logger

from cocas.domain.exceptions import (
    DecryptionError,
    InsufficientStorageError,
    VaultFileNotFoundError,
)
from cocas.domain.ports.storage import VaultCategory, VaultRef
from cocas.domain.ports.system import IClock, IIdGenerator
from cocas.infrastructure.storage.path_guard import build_relative_path, resolve_within

#: ⭐ Deliberately *not* imported from `security.crypto`. The Vault file format
#: and the DB cell format have the same shape today; sharing the constant
#: would make a version bump on either one silently bump the other, and they
#: are versioned by different concerns (file layout vs column layout).
VAULT_FORMAT_VERSION = b"\x01"

NONCE_LENGTH_BYTES = 12
VAULT_KEY_LENGTH_BYTES = 32

#: §V-CTR-008 / §10.4.1 #10 — never start a write that could fill the disk.
MIN_FREE_BYTES = 100 * 1024 * 1024

_HEADER_LENGTH = len(VAULT_FORMAT_VERSION) + NONCE_LENGTH_BYTES


class EncryptedFileVault:
    """⭐ Port 11 — AES-256-GCM file storage under `root` (§12.13)."""

    def __init__(
        self,
        root: Path,
        vault_key: bytes,
        clock: IClock,
        id_generator: IIdGenerator,
        *,
        min_free_bytes: int = MIN_FREE_BYTES,
    ) -> None:
        if len(vault_key) != VAULT_KEY_LENGTH_BYTES:
            raise ValueError(
                f"VAULT_KEY phải dài đúng {VAULT_KEY_LENGTH_BYTES} byte."
            )
        self._root = Path(root)
        self._aesgcm = AESGCM(vault_key)
        self._clock = clock
        self._ids = id_generator
        self._min_free_bytes = min_free_bytes

    @property
    def root(self) -> Path:
        """The Vault root. ⚠️ For diagnostics and backup only — never to build
        a path from caller input; that is `path_guard.resolve_within`'s job."""
        return self._root

    # ------------------------------------------------------------------ write

    def save(self, data: bytes, category: VaultCategory) -> VaultRef:
        """Encrypt and store `data`, returning its Vault-relative reference.

        Raises:
            InsufficientStorageError: below the free-space floor, or the
                write itself failed.
        """
        ref = VaultRef(
            category=category,
            relative_path=build_relative_path(
                category, self._clock.today(), self._ids.new_id()
            ),
        )
        destination = resolve_within(self._root, ref)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._check_free_space(destination.parent, len(data))

        payload = self._encrypt(data, ref)
        self._write_verify_rename(destination, payload, ref)

        logger.info(
            "Vault stored {} bytes ({} plaintext) at {}",
            len(payload),
            len(data),
            ref.relative_path,
        )
        return ref

    # ------------------------------------------------------------------- read

    def load(self, ref: VaultRef) -> bytes:
        """Read and decrypt a stored file.

        Raises:
            PathTraversalError: the reference is not one this Vault produced.
            VaultFileNotFoundError: no such file.
            DecryptionError: wrong key, wrong slot, or tampered bytes.
        """
        source = resolve_within(self._root, ref)
        try:
            payload = source.read_bytes()
        except FileNotFoundError as exc:
            raise VaultFileNotFoundError(
                "Không tìm thấy tệp trong kho dữ liệu.", path=ref.relative_path
            ) from exc
        except OSError as exc:
            raise VaultFileNotFoundError(
                f"Không đọc được tệp trong kho dữ liệu: {exc}", path=ref.relative_path
            ) from exc
        return self._decrypt(payload, ref)

    def exists(self, ref: VaultRef) -> bool:
        return resolve_within(self._root, ref).is_file()

    def delete(self, ref: VaultRef) -> None:
        """Remove a stored file. Idempotent (§12.13).

        ⚠️ The path guard runs here too. Without it this method would be an
        arbitrary-file-deletion primitive reachable from anything holding a
        `VaultRef` — and P-05's retention purge calls it in a loop.
        """
        target = resolve_within(self._root, ref)
        target.unlink(missing_ok=True)

    # -------------------------------------------------------------- internals

    def _aad(self, ref: VaultRef) -> bytes:
        return ref.relative_path.encode("utf-8")

    def _encrypt(self, data: bytes, ref: VaultRef) -> bytes:
        nonce = secrets.token_bytes(NONCE_LENGTH_BYTES)
        sealed = self._aesgcm.encrypt(nonce, data, self._aad(ref))
        return VAULT_FORMAT_VERSION + nonce + sealed

    def _decrypt(self, payload: bytes, ref: VaultRef) -> bytes:
        if len(payload) < _HEADER_LENGTH or payload[:1] != VAULT_FORMAT_VERSION:
            raise DecryptionError(
                "Tệp trong kho dữ liệu không đúng định dạng.", path=ref.relative_path
            )
        nonce = payload[len(VAULT_FORMAT_VERSION) : _HEADER_LENGTH]
        try:
            return self._aesgcm.decrypt(nonce, payload[_HEADER_LENGTH:], self._aad(ref))
        except InvalidTag as exc:
            raise DecryptionError(
                "Giải mã tệp thất bại — tệp có thể đã bị sửa đổi hoặc sai vị trí.",
                path=ref.relative_path,
            ) from exc

    def _check_free_space(self, directory: Path, incoming_bytes: int) -> None:
        free = shutil.disk_usage(directory).free
        if free - incoming_bytes < self._min_free_bytes:
            raise InsufficientStorageError(
                f"Không đủ dung lượng đĩa. Còn {free // (1024 * 1024)} MB.",
                free_bytes=free,
            )

    def _write_verify_rename(
        self, destination: Path, payload: bytes, ref: VaultRef
    ) -> None:
        """⭐ write-temp → verify → rename (§12.13), with one extra check.

        Besides re-reading the ciphertext, this **decrypts it once**. That is
        the only thing that proves `save()` and `load()` derive the same AAD
        from the same `VaultRef`: get that wrong and every file is written
        fine, hashes fine, and turns out to be unreadable years later when
        someone asks for the contract back (P-09). AES-GCM on a 200 KB
        document costs well under a millisecond — a bad trade to skip.
        """
        temporary = destination.with_name(f"{destination.name}.tmp")
        try:
            temporary.write_bytes(payload)
            written = temporary.read_bytes()
            if hashlib.sha256(written).digest() != hashlib.sha256(payload).digest():
                raise DecryptionError(
                    "Tệp ghi vào kho dữ liệu không toàn vẹn.", path=ref.relative_path
                )
            self._decrypt(written, ref)
            os.replace(temporary, destination)
        except OSError as exc:
            raise InsufficientStorageError(
                f"Không ghi được tệp vào kho dữ liệu: {exc}", path=ref.relative_path
            ) from exc
        finally:
            temporary.unlink(missing_ok=True)
