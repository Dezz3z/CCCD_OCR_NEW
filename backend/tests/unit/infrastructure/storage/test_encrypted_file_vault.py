"""§12.13 — `EncryptedFileVault`: round trip, AAD binding, and what it refuses."""
from __future__ import annotations

import secrets
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cocas.domain.exceptions import (
    DecryptionError,
    InsufficientStorageError,
    PathTraversalError,
    VaultFileNotFoundError,
)
from cocas.domain.ports.storage import IFileStorage, VaultCategory, VaultRef
from cocas.infrastructure.security.crypto import DpapiCryptoService
from cocas.infrastructure.storage.encrypted_file_vault import (
    VAULT_FORMAT_VERSION,
    EncryptedFileVault,
)
from tests.fixtures.fake_ports import FrozenClock, SequentialIdGenerator

NOW = datetime(2026, 8, 11, 9, 0, tzinfo=UTC)
PAYLOAD = "hợp đồng số 01A-KQ-202608-00042".encode()


@pytest.fixture
def vault_key() -> bytes:
    return secrets.token_bytes(32)


@pytest.fixture
def vault(tmp_path: Path, vault_key: bytes) -> EncryptedFileVault:
    return EncryptedFileVault(
        root=tmp_path / "vault",
        vault_key=vault_key,
        clock=FrozenClock(NOW),
        id_generator=SequentialIdGenerator(),
    )


def test_satisfies_the_port(vault: EncryptedFileVault) -> None:
    assert isinstance(vault, IFileStorage)


def test_round_trip(vault: EncryptedFileVault) -> None:
    ref = vault.save(PAYLOAD, VaultCategory.CONTRACT_DOCUMENT)

    assert vault.load(ref) == PAYLOAD
    assert vault.exists(ref)


def test_path_is_date_partitioned_and_uuid_named(vault: EncryptedFileVault) -> None:
    ref = vault.save(PAYLOAD, VaultCategory.CONTRACT_DOCUMENT)

    assert ref.relative_path == (
        "contract_document/2026/08/11/00000000-0000-0000-0000-000000000001.enc"
    )
    assert ref.category is VaultCategory.CONTRACT_DOCUMENT


def test_stored_bytes_are_not_the_plaintext(
    vault: EncryptedFileVault, tmp_path: Path
) -> None:
    """⭐ P-13's whole point: someone reading the directory sees nothing."""
    ref = vault.save(PAYLOAD, VaultCategory.CONTRACT_DOCUMENT)

    stored = (tmp_path / "vault" / ref.relative_path).read_bytes()

    assert PAYLOAD not in stored
    assert stored[:1] == VAULT_FORMAT_VERSION
    assert len(stored) == len(VAULT_FORMAT_VERSION) + 12 + len(PAYLOAD) + 16


def test_no_temporary_file_survives(vault: EncryptedFileVault, tmp_path: Path) -> None:
    vault.save(PAYLOAD, VaultCategory.CONTRACT_DOCUMENT)

    assert list((tmp_path / "vault").rglob("*.tmp")) == []


def test_each_save_uses_a_fresh_nonce(vault: EncryptedFileVault, tmp_path: Path) -> None:
    first = vault.save(PAYLOAD, VaultCategory.CONTRACT_DOCUMENT)
    second = vault.save(PAYLOAD, VaultCategory.CONTRACT_DOCUMENT)

    root = tmp_path / "vault"
    assert (root / first.relative_path).read_bytes() != (
        root / second.relative_path
    ).read_bytes()


# -------------------------------------------------------------- AAD binding


def test_a_file_moved_between_categories_will_not_decrypt(
    vault: EncryptedFileVault, tmp_path: Path
) -> None:
    """⭐ The §12.13.1 invariant: AAD is the path, so a `.enc` relocated into
    another slot fails authentication instead of decrypting into it."""
    ref = vault.save(PAYLOAD, VaultCategory.CARD_IMAGE)
    root = tmp_path / "vault"
    stolen = ref.relative_path.replace("card_image/", "contract_document/", 1)
    destination = root / stolen
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes((root / ref.relative_path).read_bytes())

    with pytest.raises(DecryptionError):
        vault.load(
            VaultRef(category=VaultCategory.CONTRACT_DOCUMENT, relative_path=stolen)
        )


def test_a_tampered_byte_is_detected(vault: EncryptedFileVault, tmp_path: Path) -> None:
    ref = vault.save(PAYLOAD, VaultCategory.CONTRACT_DOCUMENT)
    target = tmp_path / "vault" / ref.relative_path
    blob = bytearray(target.read_bytes())
    blob[-1] ^= 0xFF
    target.write_bytes(bytes(blob))

    with pytest.raises(DecryptionError):
        vault.load(ref)


def test_a_truncated_file_is_rejected_before_decryption(
    vault: EncryptedFileVault, tmp_path: Path
) -> None:
    ref = vault.save(PAYLOAD, VaultCategory.CONTRACT_DOCUMENT)
    (tmp_path / "vault" / ref.relative_path).write_bytes(b"\x01\x02")

    with pytest.raises(DecryptionError):
        vault.load(ref)


def test_another_vault_key_cannot_read_it(
    vault: EncryptedFileVault, tmp_path: Path
) -> None:
    ref = vault.save(PAYLOAD, VaultCategory.CONTRACT_DOCUMENT)
    other = EncryptedFileVault(
        root=tmp_path / "vault",
        vault_key=secrets.token_bytes(32),
        clock=FrozenClock(NOW),
        id_generator=SequentialIdGenerator(),
    )

    with pytest.raises(DecryptionError):
        other.load(ref)


def test_vault_key_is_not_the_kek(tmp_path: Path) -> None:
    """⭐ §12.13.1 — the Vault must not be readable with the cell-encryption key.

    If someone "simplifies" the Container by passing `kek` straight in, this
    is what notices: the derived key and the KEK are different secrets, and
    the file written under one does not open under the other.
    """
    kek = secrets.token_bytes(32)
    crypto = DpapiCryptoService(kek)
    assert crypto.vault_key != kek

    real = EncryptedFileVault(
        root=tmp_path / "vault",
        vault_key=crypto.vault_key,
        clock=FrozenClock(NOW),
        id_generator=SequentialIdGenerator(),
    )
    ref = real.save(PAYLOAD, VaultCategory.CONTRACT_DOCUMENT)

    mistaken = EncryptedFileVault(
        root=tmp_path / "vault",
        vault_key=kek,
        clock=FrozenClock(NOW),
        id_generator=SequentialIdGenerator(),
    )
    with pytest.raises(DecryptionError):
        mistaken.load(ref)


def test_a_short_key_is_refused_at_construction(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="32 byte"):
        EncryptedFileVault(
            root=tmp_path,
            vault_key=b"too-short",
            clock=FrozenClock(NOW),
            id_generator=SequentialIdGenerator(),
        )


# --------------------------------------------------------------- read/delete


def test_missing_file_raises_not_found(vault: EncryptedFileVault) -> None:
    ref = VaultRef(
        category=VaultCategory.CONTRACT_DOCUMENT,
        relative_path="contract_document/2026/08/11/"
        "00000000-0000-0000-0000-0000000000ff.enc",
    )

    assert not vault.exists(ref)
    with pytest.raises(VaultFileNotFoundError):
        vault.load(ref)


def test_delete_is_idempotent(vault: EncryptedFileVault) -> None:
    ref = vault.save(PAYLOAD, VaultCategory.CONTRACT_DOCUMENT)

    vault.delete(ref)
    vault.delete(ref)

    assert not vault.exists(ref)


def test_delete_also_runs_the_path_guard(vault: EncryptedFileVault) -> None:
    """⚠️ Otherwise `delete()` is an arbitrary-file-deletion primitive, and
    P-05's retention purge calls it in a loop."""
    with pytest.raises(PathTraversalError):
        vault.delete(
            VaultRef(
                category=VaultCategory.CARD_IMAGE,
                relative_path="../../../important.txt",
            )
        )


def test_load_refuses_a_traversal_reference(vault: EncryptedFileVault) -> None:
    with pytest.raises(PathTraversalError):
        vault.load(
            VaultRef(
                category=VaultCategory.CARD_IMAGE,
                relative_path="card_image/2026/08/11/../../../../etc/passwd",
            )
        )


# ------------------------------------------------------------- disk pressure


def test_refuses_to_write_below_the_free_space_floor(
    tmp_path: Path, vault_key: bytes
) -> None:
    tight = EncryptedFileVault(
        root=tmp_path / "vault",
        vault_key=vault_key,
        clock=FrozenClock(NOW),
        id_generator=SequentialIdGenerator(),
        min_free_bytes=1 << 62,
    )

    with pytest.raises(InsufficientStorageError):
        tight.save(PAYLOAD, VaultCategory.CONTRACT_DOCUMENT)

    assert list((tmp_path / "vault").rglob("*.enc")) == []
