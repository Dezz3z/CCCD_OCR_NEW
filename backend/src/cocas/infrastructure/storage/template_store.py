"""Template Store — the **plaintext** half of §11's storage layout.

⚠️ Deliberately not the Vault, and deliberately not encrypted. Two reasons,
both structural rather than convenience:

  1. `DocxRenderer` opens a template **by path** (`render_to_bytes(
     template_path, …)`) and caches the prepared Jinja environment by
     `(path, sha256)`. Routing it through `IFileStorage` would mean decrypting
     2–3 MB on every contract just to hand the bytes back to a component that
     wanted a file.
  2. A template contains no customer data — only `{{placeholders}}`. §4.8.3
     puts "every file in the Vault" in the encrypted column because those
     files are images of ID cards and finished contracts. A template is
     neither, so encrypting it would buy nothing and cost the cache.

It still uses **write-temp → verify SHA-256 → rename**, because a half-written
template is a template that renders a truncated legal document.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path

from cocas.domain.exceptions import PathTraversalError, TemplateNotFoundError

#: `{template_code}/v{n}/template.docx` — the one shape `save()` produces.
#:
#: ⭐ Mirrors `backend/resources/templates/` exactly, so seeding the store is a
#: plain copy rather than a rename step that could disagree with itself.
_RELATIVE_PATH_PATTERN = re.compile(r"^[A-Z0-9_]{1,50}/v\d{1,4}/template\.docx$")

TEMPLATE_FILENAME = "template.docx"


@dataclass(frozen=True, slots=True)
class StoredTemplate:
    """Where a template version landed, and what it hashes to."""

    relative_path: str
    sha256: bytes
    size_bytes: int


def build_relative_path(template_code: str, version_no: int) -> str:
    """The store-relative path for one version of one template."""
    return f"{template_code}/v{version_no}/{TEMPLATE_FILENAME}"


def assert_valid_shape(relative_path: str) -> None:
    """Raise `PathTraversalError` unless `relative_path` is one we produced.

    Same reasoning as `path_guard.assert_valid_shape` — see that module for
    why the shape is checked *before* the join rather than trusting `/` to
    keep the result under the root on Windows.
    """
    if not _RELATIVE_PATH_PATTERN.match(relative_path):
        raise PathTraversalError(
            "Đường dẫn mẫu hợp đồng không hợp lệ.",
            details={"relative_path": relative_path},
        )


class TemplateStore:
    """Reads and writes `.docx` templates under one root directory."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    @property
    def root(self) -> Path:
        return self._root

    def resolve(self, relative_path: str) -> Path:
        """Absolute path for a store-relative path, or raise `PathTraversalError`."""
        assert_valid_shape(relative_path)
        resolved_root = self._root.resolve()
        candidate = (resolved_root / relative_path).resolve()
        if not candidate.is_relative_to(resolved_root):
            raise PathTraversalError(
                "Đường dẫn mẫu hợp đồng nằm ngoài kho mẫu.",
                details={"relative_path": relative_path},
            )
        return candidate

    def save(self, data: bytes, template_code: str, version_no: int) -> StoredTemplate:
        """Write one template version; returns where it went and its digest."""
        relative_path = build_relative_path(template_code, version_no)
        destination = self.resolve(relative_path)
        destination.parent.mkdir(parents=True, exist_ok=True)

        digest = hashlib.sha256(data).digest()
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        try:
            temporary.write_bytes(data)
            if hashlib.sha256(temporary.read_bytes()).digest() != digest:
                raise TemplateNotFoundError(
                    "Ghi mẫu hợp đồng thất bại: nội dung đọc lại không khớp.",
                    details={"relative_path": relative_path},
                )
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

        return StoredTemplate(
            relative_path=relative_path, sha256=digest, size_bytes=len(data)
        )

    def load(self, relative_path: str) -> bytes:
        """Read one template version, or raise `TemplateNotFoundError`."""
        path = self.resolve(relative_path)
        if not path.is_file():
            raise TemplateNotFoundError(
                "Không tìm thấy file mẫu hợp đồng.",
                details={"relative_path": relative_path},
            )
        return path.read_bytes()

    def exists(self, relative_path: str) -> bool:
        return self.resolve(relative_path).is_file()
