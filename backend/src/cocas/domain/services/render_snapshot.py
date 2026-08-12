"""Canonical form of a render snapshot, and its digest (§4.4.10).

`contract.snapshot_sha256` exists to "chứng minh snapshot không bị sửa" — it
is the hash of the render **context**, the thing stored encrypted next to it in
`render_snapshot_enc`. That only works if the bytes hashed and the bytes
encrypted are produced the same way, so both come from `canonical_bytes()`
here rather than from two `json.dumps` calls that agree until one of them
gains a keyword argument.

🔴 Added 2026-08-12, first real `POST /contracts/generate`. Two defects met at
this column:

  * **The wrong hash was being stored.** `mark_completed()` was handed the
    `.docx` digest, which `contract_document.file_sha256` already holds — so
    the document's integrity was recorded twice and the snapshot's not at all.
  * **It was being stored too late.** The column is NOT NULL (§4.4.10) and the
    row is INSERTed at `GENERATING` **before** rendering (§12.14.2), so a value
    that only appears at `COMPLETED` cannot satisfy the INSERT. The real
    `SqlAlchemyContractRepository` refused the row and said so; the fake
    repository in module 6's harness had no such column and did not.

The snapshot is fully known at T1 — it is the input to the render, not its
output — so the digest belongs on the entity from construction.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


def canonical_bytes(snapshot: Mapping[str, Any]) -> bytes:
    """The exact bytes that get encrypted into `render_snapshot_enc`.

    `sort_keys=True` makes the form independent of dict ordering, so the same
    context hashes the same on any run — which is what P-09 ("in lại sau 5 năm
    giống bản gốc") needs from an integrity check. `ensure_ascii=False` keeps
    Vietnamese readable when the blob is decrypted for an audit.
    """
    return json.dumps(dict(snapshot), ensure_ascii=False, sort_keys=True).encode("utf-8")


def digest(snapshot: Mapping[str, Any]) -> bytes:
    """SHA-256 over `canonical_bytes()` — the value of `snapshot_sha256`."""
    return hashlib.sha256(canonical_bytes(snapshot)).digest()
