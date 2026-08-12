"""Document rendering port (§12.11) — port 12 of 18.

⭐ D2.1 — `IPdfConverter` (port 13) và `PdfResult` đã bị gỡ cùng toàn bộ
khâu xuất PDF; xem §9.13 và §12.12. `IDocumentRenderer` là **điểm cuối**
của chuỗi sinh tài liệu: sau nó không còn bước chuyển đổi nào nữa.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class RenderedDocument:
    """A rendered `.docx` still in memory (§12.11.2).

    ⭐ `sha256` is the hash of `content` — the **plaintext** document. That is
    what `contract_document.file_sha256` stores and what §9.15 re-checks on
    every download; hashing the Vault's ciphertext instead would give an
    unchanged contract a new hash on every re-encryption (fresh nonce).
    """

    content: bytes
    sha256: bytes
    size_bytes: int
    duration_ms: int


@dataclass(frozen=True, slots=True)
class RenderResult:
    """Outcome of rendering a `.docx` from a template to a file."""

    output_path: str
    sha256: bytes
    size_bytes: int
    duration_ms: int


@runtime_checkable
class IDocumentRenderer(Protocol):
    """⭐ Port 12 — render a template to `.docx` (§12.11).

    The context passed in contains only primitives and already-adapted
    rich-text objects; building it is `RenderContextBuilder`'s job
    (Application) and adapting `StyledValue` is `DocxContextAdapter`'s
    (Infrastructure). This port never sees a `StyledValue`.

    Invariant: write-temp → verify → rename, so a half-written `.docx`
    never exists at `output_path`.
    """

    def render_to_bytes(
        self,
        template_path: str,
        context: dict[str, object],
        expected_sha256: bytes | None = None,
    ) -> RenderedDocument:
        """⭐ Render and return the document without touching the filesystem.

        This exists because Port 11 and Port 12 do not compose (§12.11.2):
        `IFileStorage.save()` takes `bytes`, this port writes to a path, and
        the only bridge between them is a temporary file — which would put an
        **unencrypted** contract on disk, contradicting §4.8.3 ("toàn bộ file
        trong Vault" is encrypted) and §10's T9. Contract generation uses
        this; the template preview (§9.10), whose whole point is a plain file
        outside the Vault, uses `render()`.

        Raises the same set as `render()` minus `DocumentIntegrityError`,
        which is about a file that was written and read back.
        """
        ...

    def render(
        self,
        template_path: str,
        context: dict[str, object],
        output_path: str,
        expected_sha256: bytes | None = None,
    ) -> RenderResult:
        """Render and return the result.

        ⭐ `expected_sha256` is a **parameter**, not something the adapter can
        look up: §12.11 makes "SHA-256 matches the CSDL" a precondition and
        lists `TemplateChecksumMismatchError` among the raises, but
        Infrastructure must not read the database to find the recorded value.
        Without it the precondition is unchecked and the exception unreachable.

        Raises:
            TemplateNotFoundError: template file missing.
            TemplateChecksumMismatchError: on-disk SHA-256 ≠ `expected_sha256`.
            RenderError: rendering failed.
            InsufficientStorageError: less than the required free space.
            DocumentIntegrityError: the file read back does not match what
                was written (`COCAS-7009`).
        """
        ...
