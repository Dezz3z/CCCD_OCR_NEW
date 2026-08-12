"""Vault path construction and validation (§10.4.2, §12.13.2).

⭐ Its own module, not a private helper inside `EncryptedFileVault`, because
three callers need exactly this check: the Vault itself, the download endpoint
(§5.3.9) and the weekly integrity-reconciliation job (§9.15). A second copy of
a security check is a copy that will drift.

## ⚠️ Why the shape is validated *before* the join

On Windows, `pathlib`'s `/` gives no protection at all — an absolute or
drive-rooted right-hand side **replaces** the left:

    PureWindowsPath("C:/vault") / "C:/Windows/x"  ->  C:/Windows/x
    PureWindowsPath("C:/vault") / "/Windows/x"    ->  C:/Windows/x

`resolve()` + `is_relative_to()` still catches those, but only because of that
second check; reading "we joined it onto the root" and concluding "so it is
under the root" is a wrong inference that spreads. So a string that does not
match the exact shape this system produces never becomes a `Path` at all.
"""
from __future__ import annotations

import re
import uuid
from datetime import date
from pathlib import Path

from cocas.domain.exceptions import PathTraversalError
from cocas.domain.ports.storage import VaultCategory, VaultRef

#: The one shape `save()` ever produces: `{category}/{yyyy}/{mm}/{dd}/{uuid}.enc`.
#: ⚠️ Only forward slashes — a stored path is a portable reference, not a
#: Windows path, and a backslash in it means someone hand-built the string.
_CATEGORIES = "|".join(category.value for category in VaultCategory)
_RELATIVE_PATH_PATTERN = re.compile(
    rf"^({_CATEGORIES})/\d{{4}}/\d{{2}}/\d{{2}}/"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.enc$"
)

ENCRYPTED_SUFFIX = ".enc"


def build_relative_path(category: VaultCategory, on: date, file_id: uuid.UUID) -> str:
    """The Vault-relative path for a new file (§12.13 postcondition).

    ⭐ Date-partitioned so a directory never grows past a few thousand
    entries, and so `RETENTION_PURGE` (P-05) can drop a whole day's card
    images by walking one folder instead of querying for candidates.
    """
    return (
        f"{category.value}/{on.year:04d}/{on.month:02d}/{on.day:02d}/"
        f"{file_id}{ENCRYPTED_SUFFIX}"
    )


def assert_valid_shape(relative_path: str) -> None:
    """Raise `PathTraversalError` unless `relative_path` is one we produced.

    This rejects `..`, absolute paths, drive letters, UNC prefixes, NTFS
    alternate data streams and stray backslashes in one predicate, because
    all of them fail the same positive match.
    """
    if not _RELATIVE_PATH_PATTERN.match(relative_path):
        raise PathTraversalError(
            "Đường dẫn tệp trong kho không hợp lệ.", path=relative_path
        )


def resolve_within(root: Path, ref: VaultRef) -> Path:
    """Absolute path of `ref` inside `root`, proven to stay inside it.

    Raises:
        PathTraversalError: the shape is wrong, the category disagrees with
            the path, or the resolved path escaped the Vault root.
    """
    assert_valid_shape(ref.relative_path)

    # ⭐ The category is part of the AAD, so a `VaultRef` whose declared
    # category disagrees with its path would fail to decrypt anyway — but it
    # would fail as `DecryptionError`, which reads as "the file is corrupt"
    # when in fact the caller built the ref wrong.
    if not ref.relative_path.startswith(f"{ref.category.value}/"):
        raise PathTraversalError(
            "Loại tệp không khớp đường dẫn trong kho.", path=ref.relative_path
        )

    resolved_root = root.resolve()
    candidate = (resolved_root / ref.relative_path).resolve()
    if not candidate.is_relative_to(resolved_root):
        raise PathTraversalError(
            "Đường dẫn tệp nằm ngoài kho dữ liệu.", path=ref.relative_path
        )
    return candidate
