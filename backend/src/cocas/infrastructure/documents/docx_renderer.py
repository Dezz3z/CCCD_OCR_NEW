"""`DocxRenderer` — ⭐ Port 12 `IDocumentRenderer` (§12.11, §9.12).

⭐ **This does not call `DocxTemplate.render()`.** Measured 2026-08-11 on the
two real templates: docxtpl's own render+save takes **14.4 s** and **33.6 s**
against an 800 ms budget (NFR-03), and 63% of that is `map_tree` — three
lines that splice a 57 000-element lxml subtree into `python-docx`'s object
model purely so `save()` can serialise it back out. We already hold the
rendered XML as a string; the round trip buys nothing.

So the work is split the way the measurement splits it (§9.12.1):

| Phase | Depends on | Cost | Cached |
|---|---|---|---|
| `_prepare` | the template file alone | 5.5–8.9 s | ⭐ yes, by `(path, sha256)` |
| `render`   | prepared template + context | 0.31–0.64 s | no |

docxtpl is still the library — `patch_xml` (run healing), `fix_tables`
(column counts after a loop) and `fix_docpr_ids` (drawing IDs) are used
verbatim. Only its top-level `render()`/`save()` are bypassed.

⚠️ Not supported as a consequence, all unused in v1.0: Jinja2 inside
`docProps/core.xml`, `InlineImage`, `SubDoc`, and picture replacement — every
one of them needs the object model this class deliberately does not build.
"""
from __future__ import annotations

import hashlib
import io
import os
import re
import shutil
import time
import zipfile
from collections import OrderedDict
from pathlib import Path

from docxtpl import DocxTemplate
from jinja2 import Template as JinjaTemplate
from jinja2 import Undefined
from jinja2.exceptions import TemplateError
from jinja2.sandbox import SandboxedEnvironment
from loguru import logger
from lxml import etree

from cocas.domain.exceptions import (
    DocumentIntegrityError,
    InsufficientStorageError,
    RenderError,
    TemplateChecksumMismatchError,
    TemplateNotFoundError,
)
from cocas.domain.ports.documents import RenderResult
from cocas.infrastructure.documents.template_inspector import ALLOWED_FILTERS

#: Parts that may contain Jinja2. Everything else in the zip is copied byte
#: for byte — including `word/media/*`, which is most of the file size.
_RENDERABLE_PART = re.compile(r"^word/(document|header\d*|footer\d*|footnotes|endnotes)\.xml$")

_MAIN_PART = "word/document.xml"
_XML_DECLARATION = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'

#: §12.11 precondition — refuse to start a write that could fill the disk.
_MIN_FREE_BYTES = 100 * 1024 * 1024

#: v1.0 ships 2 templates; 4 leaves room for a version bump on each without
#: evicting the other. Each entry holds the template's own bytes (~0.9 MB).
_DEFAULT_CACHE_SIZE = 4


class _EmptyUndefined(Undefined):
    """⭐ §9.8 — a missing variable renders as nothing, never as `"None"`.

    Not `StrictUndefined`: that raises *mid-render*, leaving a half-filled
    contract. Missing values are caught **before** rendering by
    `RenderContextBuilder.missing_required_variables` (`COCAS-7002`).
    """

    __slots__ = ()

    def _log(self) -> None:
        logger.debug("Template referenced an undefined variable: {}", self._undefined_name)

    def __str__(self) -> str:
        self._log()
        return ""

    def __html__(self) -> str:
        self._log()
        return ""


class _PreparedTemplate:
    """One template file, patched and compiled — everything reusable."""

    __slots__ = ("blobs", "compiled", "fix_docpr_ids", "fix_tables", "infos", "sha256")

    def __init__(self, data: bytes, sha256: bytes, env: SandboxedEnvironment) -> None:
        self.sha256 = sha256
        docx_template = DocxTemplate(io.BytesIO(data))
        docx_template.init_docx(reload=False)
        # ⚠️ `render_init()` is what creates `docx_ids_index`; without it
        # `fix_docpr_ids` raises AttributeError on the first call.
        docx_template.render_init()
        self.fix_tables = docx_template.fix_tables
        self.fix_docpr_ids = docx_template.fix_docpr_ids

        self.compiled: dict[str, JinjaTemplate] = {}
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.infos = archive.infolist()
            self.blobs = {info.filename: archive.read(info.filename) for info in self.infos}

        for name, blob in self.blobs.items():
            if _RENDERABLE_PART.match(name):
                self.compiled[name] = env.from_string(docx_template.patch_xml(_to_body(blob)))


class DocxRenderer:
    """⭐ Port 12 — render a `.docx` template to a `.docx` file (§12.11)."""

    def __init__(
        self, *, cache_size: int = _DEFAULT_CACHE_SIZE, min_free_bytes: int = _MIN_FREE_BYTES
    ) -> None:
        self._cache: OrderedDict[tuple[str, bytes], _PreparedTemplate] = OrderedDict()
        self._cache_size = cache_size
        self._min_free_bytes = min_free_bytes

    def prepare(self, template_path: str, expected_sha256: bytes | None = None) -> None:
        """Populate the cache ahead of the first contract (§9.17).

        The first render of a template otherwise pays 6–9 s. Calling this at
        startup moves that cost off the user's critical path — the same
        reason `PaddleOcrAdapter.warm_up()` exists.
        """
        self._load(template_path, expected_sha256)

    def render(
        self,
        template_path: str,
        context: dict[str, object],
        output_path: str,
        expected_sha256: bytes | None = None,
    ) -> RenderResult:
        """Render `context` into `output_path` and return the result.

        Raises:
            TemplateNotFoundError: the template file is missing.
            TemplateChecksumMismatchError: on-disk SHA-256 ≠ `expected_sha256`.
            InsufficientStorageError: less than 100 MB free at the destination.
            RenderError: Jinja2 failed, or the produced zip is not a `.docx`.
            DocumentIntegrityError: the file read back does not hash to what
                was written (`COCAS-7009`).
        """
        started = time.perf_counter()
        prepared = self._load(template_path, expected_sha256)
        destination = Path(output_path)
        self._check_free_space(destination)

        payload = self._build_docx(prepared, context)
        digest = hashlib.sha256(payload).digest()
        self._write_verify_rename(destination, payload, digest)

        duration_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "Rendered document: {} bytes in {} ms", len(payload), duration_ms
        )
        return RenderResult(
            output_path=str(destination),
            sha256=digest,
            size_bytes=len(payload),
            duration_ms=duration_ms,
        )

    # -------------------------------------------------------------- preparing

    def _load(self, template_path: str, expected_sha256: bytes | None) -> _PreparedTemplate:
        source = Path(template_path)
        try:
            data = source.read_bytes()
        except OSError as exc:
            raise TemplateNotFoundError(
                f"Không tìm thấy file mẫu: {source.name}", path=source.name
            ) from exc

        # ⭐ Hash on every call, not only on a cache miss. The cache key is
        # `(path, sha256)`, so a template edited in place — restore from
        # backup, disk corruption, someone "fixing" the file — misses the
        # cache and is re-prepared instead of silently rendering the old one.
        actual = hashlib.sha256(data).digest()
        if expected_sha256 is not None and actual != expected_sha256:
            raise TemplateChecksumMismatchError(
                "File mẫu đã bị thay đổi. Cần đăng ký lại mẫu.", path=source.name
            )

        key = (str(source.resolve()), actual)
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached

        started = time.perf_counter()
        try:
            prepared = _PreparedTemplate(data, actual, self._make_env())
        except (TemplateError, zipfile.BadZipFile, etree.XMLSyntaxError, ValueError) as exc:
            raise RenderError(
                f"Không đọc được mẫu hợp đồng: {exc}", path=source.name
            ) from exc

        self._cache[key] = prepared
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        logger.info(
            "Prepared template {} in {} ms ({} renderable parts)",
            source.name,
            int((time.perf_counter() - started) * 1000),
            len(prepared.compiled),
        )
        return prepared

    def _make_env(self) -> SandboxedEnvironment:
        """⭐ §9.9 measure #2 — the sandbox plus a filter whitelist.

        `TemplateInspector` already rejects a non-whitelisted filter at
        registration (`COCAS-6014`). This is the second net: a template that
        somehow reached the disk without passing inspection still cannot call
        `|attr` or `|pprint` here.
        """
        env = SandboxedEnvironment(undefined=_EmptyUndefined, autoescape=False)
        env.filters = {name: env.filters[name] for name in ALLOWED_FILTERS if name in env.filters}
        env.globals.clear()
        return env

    # -------------------------------------------------------------- rendering

    def _build_docx(self, prepared: _PreparedTemplate, context: dict[str, object]) -> bytes:
        buffer = io.BytesIO()
        try:
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                for info in prepared.infos:
                    archive.writestr(info, self._part_bytes(prepared, info.filename, context))
        except TemplateError as exc:
            raise RenderError(f"Lỗi khi dựng nội dung hợp đồng: {exc}") from exc
        return buffer.getvalue()

    def _part_bytes(
        self, prepared: _PreparedTemplate, name: str, context: dict[str, object]
    ) -> bytes:
        compiled = prepared.compiled.get(name)
        if compiled is None:
            return prepared.blobs[name]

        rendered = compiled.render(context)
        if name != _MAIN_PART:
            return _XML_DECLARATION + rendered.encode("utf-8")

        # ⭐ Kept from docxtpl even though both v1.0 templates have no loops:
        # 156 ms buys correctness for the first template that puts a
        # `{% for %}` inside a table, where the column count no longer
        # matches the grid.
        tree = prepared.fix_tables(rendered)
        prepared.fix_docpr_ids(tree)
        result: bytes = etree.tostring(
            tree, xml_declaration=True, encoding="UTF-8", standalone=True
        )
        return result

    # ---------------------------------------------------------------- writing

    def _check_free_space(self, destination: Path) -> None:
        parent = destination.parent
        parent.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(parent).free
        if free < self._min_free_bytes:
            raise InsufficientStorageError(
                f"Không đủ dung lượng đĩa. Còn {free // (1024 * 1024)} MB.",
                free_bytes=free,
            )

    def _write_verify_rename(self, destination: Path, payload: bytes, digest: bytes) -> None:
        """⭐ §9.12 — write `.tmp`, read it back, compare, then `os.replace()`.

        Reading back is not paranoia about our own bytes: it is the only way
        to notice a truncated write or a disk that accepted the data and lost
        it. `os.replace()` is atomic on NTFS, so no half-written `.docx` can
        ever appear at `destination`.
        """
        temporary = destination.with_name(f"{destination.name}.tmp")
        try:
            temporary.write_bytes(payload)
            written = hashlib.sha256(temporary.read_bytes()).digest()
            if written != digest:
                raise DocumentIntegrityError(
                    "Tài liệu ghi ra không toàn vẹn. Vui lòng thử lại.",
                    path=destination.name,
                )
            os.replace(temporary, destination)
        except OSError as exc:
            raise InsufficientStorageError(
                f"Không ghi được tài liệu: {exc}", path=destination.name
            ) from exc
        finally:
            temporary.unlink(missing_ok=True)


def _to_body(blob: bytes) -> str:
    """Return a part's XML as text **without** the `<?xml …?>` declaration.

    ⚠️ Not cosmetic. `docxtpl.fix_tables()` feeds the string straight to
    `etree.fromstring`, which refuses a `str` that still declares an
    encoding — the error reads `Unicode strings with encoding declaration are
    not supported` and points at lxml, not at us. docxtpl's own `get_xml()`
    round-trips through lxml for exactly this reason.
    """
    return str(etree.tostring(etree.fromstring(blob), encoding="unicode"))
