"""`ITemplateInspector` (Port 20) — analyse a `.docx` template (§12.8).

⭐ **It parses; it never renders.** A hostile `.docx` must not be able to
execute anything by being uploaded, so nothing here ever builds a Jinja2
template object or evaluates an expression — only `Environment.parse()`,
which produces an AST and runs no user code.

Three things about `docxtpl` shape this module, all measured on 0.18.0 against
the project's two real templates (2026-08-11):

1. ⭐ **`patch_xml()` erases the docxtpl markers before Jinja2 sees anything.**
   `{{r securities_account_no }}` reaches the parser as `{{ securities_account_no }}`,
   and `{%p … %}` as `{% … %}`. So `richtext_vars`, `COCAS-6008` and
   `COCAS-6010` **cannot** be derived from the AST; they are found by scanning
   the text (§12.8.2). The "AST, not regex" invariant governs *variable
   collection*, which is where regex actually gets things wrong.
2. ⭐ **Header and footer are separate parts.** `get_xml()` returns only
   `word/document.xml`. Both real templates carry a footer; skipping it would
   make a footer variable count as "declared by `party_schema` but unused"
   (`COCAS-6011`) — a warning about the user's correct file.
3. ⭐ **Jinja2 line numbers become paragraph ordinals** once a newline is
   inserted before each `<w:p>` (docxtpl's own trick in `render_xml_part`).
   `.docx` has no lines, so that is the only number a user can act on.

⚠️ **The design's original security scan rejects every `.docx` in existence.**
Scanning raw XML for the blacklist matches `open` inside
`http://schemas.openxmlformats.org/…`, the mandatory namespace of the format
itself — 101 hits in `01A_HD_GDN.docx`, 15 in `01A_HD_GDKQ.docx`. The scan
here runs on AST shape first (§9.9.1's five rules) and applies the substring
blacklist only to the bodies of `{{ … }}` / `{% … %}` tags, where both real
templates score zero.
"""
from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Iterable, Iterator, Mapping, Sequence
from typing import TYPE_CHECKING

from docxtpl import DocxTemplate
from jinja2 import Environment, meta, nodes
from jinja2.exceptions import TemplateSyntaxError as JinjaSyntaxError
from loguru import logger

from cocas.domain.exceptions import NotADocxFileError, TemplateSyntaxError
from cocas.domain.ports.templates import (
    DiagnosticSeverity,
    TemplateDiagnostic,
    TemplateInspection,
)
from cocas.domain.services.template_variables import (
    BOLD_VARIABLE_KEYS,
    SYSTEM_VARIABLE_KEYS,
)

if TYPE_CHECKING:
    from jinja2.nodes import Template as JinjaTemplate

_ZIP_MAGIC = b"PK\x03\x04"
_MAIN_PART = "word/document.xml"

#: 10 MB — above this the file almost certainly carries a background image
#: it does not need (`COCAS-6015`, a warning only).
_LARGE_FILE_BYTES = 10 * 1024 * 1024

#: §9.9 measure #2 — the only filters the renderer's sandbox will accept.
ALLOWED_FILTERS = frozenset(
    {"upper", "lower", "title", "trim", "default", "length", "join", "replace", "first", "last"}
)

#: §9.9.1 rule 4 — names Jinja2 puts in every template's global namespace, plus
#: the web-framework names an SSTI payload copied off the internet will try.
#: None of them is a legitimate contract variable.
_DANGEROUS_NAMES = frozenset(
    {
        "self",
        "config",
        "request",
        "session",
        "g",
        "url_for",
        "get_flashed_messages",
        "lipsum",
        "cycler",
        "joiner",
        "namespace",
        "range",
        "dict",
    }
)

#: §9.9 measure #3, corrected by §9.9.1 — the second net, applied ONLY to the
#: text inside Jinja2 tags. Applied to the raw XML it matches `openxmlformats`
#: and rejects every Word document ever produced.
_DANGEROUS_SUBSTRINGS = (
    "__",
    "mro",
    "subclasses",
    "globals",
    "builtins",
    "import",
    "eval",
    "exec",
    "popen",
    "os.",
    "sys.",
    "lipsum",
    "cycler",
    "namespace",
)

_JINJA_TAG_RE = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.DOTALL)
_XML_TAG_RE = re.compile(r"<[^>]+>")
_PARAGRAPH_SPLIT_RE = re.compile(r"<w:p([ >])")

#: docxtpl's own prefixes. Not Jinja2 syntax — they are gone by parse time.
_RICHTEXT_RE = re.compile(r"\{\{r\s+([A-Za-z_][\w.]*)")
_IMAGE_TAG_RE = re.compile(r"\{\{p\s|\{%p\s")


class DocxTemplateInspector:
    """⭐ Port 20 — the production `ITemplateInspector` (§12.8).

    Stateless and reusable: one instance can be shared for the process
    lifetime, which is how `Container` holds it.
    """

    def __init__(self) -> None:
        # ⭐ A plain Environment, not the renderer's SandboxedEnvironment:
        # sandboxing constrains *evaluation*, and nothing here evaluates.
        # Using the sandbox would suggest a protection that parsing does not
        # provide — the payloads in §9.9.1 all parse cleanly either way.
        self._env = Environment(autoescape=True)

    # ------------------------------------------------------------------ API

    def inspect(
        self,
        file_bytes: bytes,
        party_schema: Sequence[Mapping[str, object]],
        contract_fields: Sequence[Mapping[str, object]] = (),
    ) -> TemplateInspection:
        """Inspect an uploaded `.docx`. See `ITemplateInspector.inspect`."""
        template, parts = _open_docx(file_bytes)

        declared: set[str] = set()
        richtext: set[str] = set()
        loop_roots: set[str] = set()
        has_loops = False
        has_conditionals = False
        diagnostics: list[TemplateDiagnostic] = []

        for part_name, raw_xml in parts:
            source = _line_per_paragraph(_patch(template, raw_xml))
            tree = self._parse(source, part_name)
            roots = meta.find_undeclared_variables(tree)

            declared |= _collect_paths(tree, roots)
            has_loops |= any(True for _ in tree.find_all(nodes.For))
            has_conditionals |= any(True for _ in tree.find_all(nodes.If))
            loop_roots |= _loop_iteration_roots(tree, roots)
            diagnostics.extend(self._scan_security(tree, source, part_name))

            text = _flatten_to_text(raw_xml)
            richtext |= {m.group(1) for m in _RICHTEXT_RE.finditer(text)}
            diagnostics.extend(_scan_docxtpl_markers(text, part_name))

        vocabulary = _Vocabulary.build(party_schema, contract_fields)
        known, unknown = vocabulary.split(declared)
        required = tuple(sorted(p for p in known if vocabulary.is_required(p)))
        optional = tuple(sorted(p for p in known if not vocabulary.is_required(p)))

        diagnostics.extend(_warn_unknown(unknown))
        diagnostics.extend(_warn_missing_required(vocabulary, declared))
        diagnostics.extend(_warn_plain_styled(vocabulary, declared, richtext))
        diagnostics.extend(_warn_non_iterable(loop_roots, vocabulary))
        diagnostics.extend(_warn_party_schema(party_schema))
        if len(file_bytes) > _LARGE_FILE_BYTES:
            diagnostics.append(
                TemplateDiagnostic(
                    code="COCAS-6015",
                    severity=DiagnosticSeverity.WARNING,
                    message="File khá lớn — có thể chứa ảnh nền không cần thiết.",
                )
            )

        ordered = _errors_first(diagnostics)
        inspection = TemplateInspection(
            status=TemplateInspection.status_for(ordered),
            declared=tuple(sorted(declared)),
            required=required,
            optional=optional,
            unknown=tuple(sorted(unknown)),
            richtext_vars=tuple(sorted(richtext)),
            has_loops=has_loops,
            has_conditionals=has_conditionals,
            diagnostics=ordered,
        )
        logger.info(
            "Template inspected: status={} declared={} unknown={} diagnostics={}",
            inspection.status.value,
            len(inspection.declared),
            len(inspection.unknown),
            len(inspection.diagnostics),
        )
        return inspection

    # -------------------------------------------------------------- parsing

    def _parse(self, source: str, part_name: str) -> JinjaTemplate:
        """Build the AST of one part's patched Jinja2 source.

        Raises:
            TemplateSyntaxError: `COCAS-6003`, with the paragraph ordinal.
        """
        try:
            return self._env.parse(source)
        except JinjaSyntaxError as exc:
            paragraph = (exc.lineno or 1) - 1
            raise TemplateSyntaxError(
                line=paragraph,
                detail=_syntax_detail(exc, source, paragraph, part_name),
            ) from exc

    # ------------------------------------------------------------- security

    def _scan_security(
        self, tree: JinjaTemplate, source: str, part_name: str
    ) -> list[TemplateDiagnostic]:
        """§9.9.1 — five AST rules, then the substring net over tag bodies."""
        findings = sorted(set(_ast_findings(tree) + _blacklist_hits(source)))
        if not findings:
            return []
        logger.warning("Template rejected as unsafe: part={} findings={}", part_name, findings)
        return [
            TemplateDiagnostic(
                code="COCAS-6014",
                severity=DiagnosticSeverity.ERROR,
                message=(
                    "Mẫu chứa cấu trúc không được phép vì lý do an toàn "
                    f"({', '.join(findings)})."
                ),
                part=part_name,
            )
        ]


# ============================================================================
# Opening the package
# ============================================================================


def _open_docx(file_bytes: bytes) -> tuple[DocxTemplate, list[tuple[str, str]]]:
    """Return the opened template and `(part_name, xml)` for every text part.

    ⭐ Format is decided by content, never by the filename (§9.2 step 1).

    Raises:
        NotADocxFileError: `COCAS-6002`.
    """
    if not file_bytes:
        raise NotADocxFileError("File rỗng — không đúng định dạng Word (.docx).")
    if not file_bytes.startswith(_ZIP_MAGIC):
        raise NotADocxFileError("File không đúng định dạng Word (.docx).")

    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile as exc:
        raise NotADocxFileError("File không đúng định dạng Word (.docx).") from exc
    if _MAIN_PART not in names:
        raise NotADocxFileError("File không đúng định dạng Word (.docx).")

    template = DocxTemplate(io.BytesIO(file_bytes))
    try:
        template.init_docx(reload=False)
        parts: list[tuple[str, str]] = [(_MAIN_PART, template.get_xml())]
        for uri in (template.HEADER_URI, template.FOOTER_URI):
            for _rel_key, part in template.get_headers_footers(uri):
                parts.append((str(part.partname).lstrip("/"), template.get_part_xml(part)))
    except NotADocxFileError:
        raise
    except Exception as exc:
        raise NotADocxFileError("File không đúng định dạng Word (.docx).") from exc
    return template, parts


def _patch(template: DocxTemplate, raw_xml: str) -> str:
    """Run docxtpl's own run-healing / tag-stripping pass over one part.

    ⭐ Safe to call for header and footer XML on the same instance —
    `patch_xml` reads nothing from `self`, and docxtpl's own
    `get_undeclared_template_variables()` uses it exactly this way.
    """
    patched: str = template.patch_xml(raw_xml)
    return patched


def _line_per_paragraph(xml: str) -> str:
    """⭐ One line per `<w:p>`, so Jinja2's `lineno - 1` is the paragraph ordinal."""
    return _PARAGRAPH_SPLIT_RE.sub(r"\n<w:p\1", xml)


def _flatten_to_text(raw_xml: str) -> str:
    """Concatenate run text, one line per paragraph.

    ⭐ Deleting every element tag is exactly what heals a `{{r foo }}` that
    Word chopped into three runs, so this needs no run-merging logic of its own.
    """
    return _XML_TAG_RE.sub("", _line_per_paragraph(raw_xml))


def _syntax_detail(
    exc: JinjaSyntaxError, source: str, paragraph: int, part_name: str
) -> str:
    """Jinja2's message plus the offending paragraph, quoted back to the user."""
    detail = exc.message or "cú pháp không hợp lệ"
    lines = source.splitlines()
    index = (exc.lineno or 1) - 1
    if 0 <= index < len(lines):
        text = _XML_TAG_RE.sub("", lines[index]).strip()
        if text:
            detail = f"{detail} — trong đoạn «{text[:120]}»"
    if part_name != _MAIN_PART:
        detail = f"{detail} (ở {part_name}, đoạn {paragraph})"
    return detail


# ============================================================================
# Walking the AST
# ============================================================================


def _terminal_expressions(tree: JinjaTemplate) -> Iterator[nodes.Node]:
    """Yield each variable expression that is not part of a longer one.

    For `{{ holder.full_name }}` this yields the `Getattr`, not the inner
    `Name` — §9.2 step 4 wants `holder.full_name`, not `holder`.
    """
    inner = {
        id(node.node)
        for node in tree.find_all((nodes.Getattr, nodes.Getitem))
        if isinstance(node.node, nodes.Name | nodes.Getattr | nodes.Getitem)
    }
    for node in tree.find_all((nodes.Name, nodes.Getattr, nodes.Getitem)):
        if id(node) not in inner:
            yield node


def _path_of(node: nodes.Node) -> str | None:
    """Render a variable expression back to `holder.full_name` / `co_holder[0]`."""
    if isinstance(node, nodes.Name):
        return node.name
    if isinstance(node, nodes.Getattr):
        base = _path_of(node.node)
        return None if base is None else f"{base}.{node.attr}"
    if isinstance(node, nodes.Getitem):
        base = _path_of(node.node)
        if base is None:
            return None
        arg = node.arg
        if isinstance(arg, nodes.Const):
            return f"{base}[{arg.value!r}]" if isinstance(arg.value, str) else f"{base}[{arg.value}]"
        return f"{base}[]"
    return None


def _root_of(path: str) -> str:
    """`co_holder[0].full_name` → `co_holder`."""
    return re.split(r"[.\[]", path, maxsplit=1)[0]


def _collect_paths(tree: JinjaTemplate, roots: set[str]) -> set[str]:
    """Variable paths the template actually reads.

    ⚠️ `roots` comes from `jinja2.meta.find_undeclared_variables`, which is what
    keeps a loop variable out: `{% for p in parties %}{{ p.name }}{% endfor %}`
    declares `parties`, not `p`. Re-deriving that scoping by hand is how a
    template ends up warning about a variable the user never wrote.
    """
    paths: set[str] = set()
    for node in _terminal_expressions(tree):
        path = _path_of(node)
        if path is not None and _root_of(path) in roots:
            paths.add(path)
    return paths


def _loop_iteration_roots(tree: JinjaTemplate, roots: set[str]) -> set[str]:
    """Root names appearing as the *iterable* of a `{% for %}`."""
    found: set[str] = set()
    for loop in tree.find_all(nodes.For):
        path = _path_of(loop.iter)
        if path is not None and _root_of(path) in roots:
            found.add(path)
    return found


def _rule_private_attributes(tree: JinjaTemplate) -> list[str]:
    """⭐ Rule 1 — `.__class__`, `._TemplateReference__context`, …

    ⚠️ Inspects `Getattr.attr`, **not** variable names. `{{ ''.__class__ }}`
    contains no `Name` node at all — its root is a string constant — so a scan
    that only looks at variable names lets that payload straight through.
    """
    return [
        f"truy cập thuộc tính nội bộ '.{node.attr}'"
        for node in tree.find_all(nodes.Getattr)
        if node.attr.startswith("_")
    ]


def _rule_private_items(tree: JinjaTemplate) -> list[str]:
    """⭐ Rule 2 — `['__class__']`, the way around rule 1."""
    return [
        f"truy cập thuộc tính nội bộ ['{node.arg.value}']"
        for node in tree.find_all(nodes.Getitem)
        if isinstance(node.arg, nodes.Const)
        and isinstance(node.arg.value, str)
        and node.arg.value.startswith("_")
    ]


def _rule_no_calls(tree: JinjaTemplate) -> list[str]:
    """⭐ Rule 3 — a contract template has no reason to call anything, and
    every published sandbox escape ends in a call."""
    return ["lời gọi hàm"] if any(True for _ in tree.find_all(nodes.Call)) else []


def _rule_global_names(tree: JinjaTemplate) -> list[str]:
    """⭐ Rule 4 — Jinja2's own globals are the ladder every payload climbs."""
    return [
        f"tên toàn cục '{node.name}'"
        for node in tree.find_all(nodes.Name)
        if node.name in _DANGEROUS_NAMES
    ]


def _rule_template_inclusion(tree: JinjaTemplate) -> list[str]:
    """⭐ Rule 5a — `{% include %}` and friends read arbitrary files (V-TPL-004)."""
    return [
        f"thẻ {tag.__name__.lower()}"
        for tag in (nodes.Include, nodes.Extends, nodes.Import, nodes.FromImport)
        if any(True for _ in tree.find_all(tag))
    ]


def _rule_filter_whitelist(tree: JinjaTemplate) -> list[str]:
    """⭐ Rule 5b — anything outside §9.9 measure #2 dies at render anyway."""
    return [
        f"bộ lọc '{node.name}' ngoài danh sách cho phép"
        for node in tree.find_all(nodes.Filter)
        if node.name not in ALLOWED_FILTERS
    ]


_AST_RULES = (
    _rule_private_attributes,
    _rule_private_items,
    _rule_no_calls,
    _rule_global_names,
    _rule_template_inclusion,
    _rule_filter_whitelist,
)


def _ast_findings(tree: JinjaTemplate) -> list[str]:
    """§9.9.1's rules. Each returns phrases naming what it objected to."""
    return [phrase for rule in _AST_RULES for phrase in rule(tree)]


def _blacklist_hits(source: str) -> list[str]:
    """⚠️ Second net only.

    ⭐ `_JINJA_TAG_RE.findall` first, **always** — that single call is the whole
    difference between §9.9's intent and §9.9.1's measured failure. Handed the
    surrounding XML, this list matches `open` inside `openxmlformats.org` and
    rejects every `.docx` in existence.
    """
    tag_text = " ".join(_JINJA_TAG_RE.findall(source)).lower()
    return [f"từ khoá '{word}'" for word in _DANGEROUS_SUBSTRINGS if word in tag_text]


# ============================================================================
# Vocabulary — what counts as a known variable for this template
# ============================================================================


class _Vocabulary:
    """The variables this particular template is allowed to use.

    ⭐ Wider than the §9.5 dictionary: `party_schema[].extra_fields` and
    `contract_fields` declare template-specific variables, and §9.6 step 3
    flattens a single party so both `full_name` and `holder.full_name` render.
    """

    def __init__(
        self,
        party_keys: frozenset[str],
        known: frozenset[str],
        required: frozenset[str],
        styled: frozenset[str],
    ) -> None:
        self.party_keys = party_keys
        self.known = known
        self.required = required
        self.styled = styled

    @classmethod
    def build(
        cls,
        party_schema: Sequence[Mapping[str, object]],
        contract_fields: Sequence[Mapping[str, object]],
    ) -> _Vocabulary:
        party_keys: set[str] = set()
        declared: set[str] = set()
        required: set[str] = set()
        styled: set[str] = set(BOLD_VARIABLE_KEYS)

        def absorb(fields: Iterable[object]) -> None:
            for raw in fields:
                if not isinstance(raw, Mapping):
                    continue
                key = raw.get("key")
                if not isinstance(key, str) or not key:
                    continue
                declared.add(key)
                if raw.get("required") is True:
                    required.add(key)
                style = raw.get("render_style")
                if isinstance(style, Mapping) and any(style.values()):
                    styled.add(key)

        for party in party_schema:
            key = party.get("key")
            if isinstance(key, str) and key:
                party_keys.add(key)
            extra = party.get("extra_fields")
            if isinstance(extra, Sequence) and not isinstance(extra, str | bytes):
                absorb(extra)
        absorb(contract_fields)

        return cls(
            party_keys=frozenset(party_keys),
            known=frozenset(SYSTEM_VARIABLE_KEYS | declared),
            required=frozenset(required),
            styled=frozenset(styled),
        )

    def leaf_of(self, path: str) -> str:
        """`holder.full_name` → `full_name`; `full_name` → `full_name`."""
        head, _, tail = path.rpartition(".")
        return tail if head and _root_of(path) in self.party_keys else path

    def is_known(self, path: str) -> bool:
        leaf = self.leaf_of(path)
        return leaf in self.known and "[" not in leaf

    def is_required(self, path: str) -> bool:
        return self.leaf_of(path) in self.required

    def split(self, declared: Iterable[str]) -> tuple[set[str], set[str]]:
        known, unknown = set(), set()
        for path in declared:
            (known if self.is_known(path) else unknown).add(path)
        return known, unknown


# ============================================================================
# Diagnostics
# ============================================================================


def _warn_unknown(unknown: Iterable[str]) -> list[TemplateDiagnostic]:
    return [
        TemplateDiagnostic(
            code="COCAS-6009",
            severity=DiagnosticSeverity.WARNING,
            message=(
                f"Biến '{path}' không xác định — sẽ được thay bằng chuỗi rỗng. "
                "Nếu cần, khai báo ở 'Trường bổ sung'."
            ),
            variable=path,
        )
        for path in sorted(unknown)
    ]


def _warn_missing_required(
    vocabulary: _Vocabulary, declared: Iterable[str]
) -> list[TemplateDiagnostic]:
    used = {vocabulary.leaf_of(path) for path in declared}
    return [
        TemplateDiagnostic(
            code="COCAS-6011",
            severity=DiagnosticSeverity.WARNING,
            message=f"Mẫu khai báo cần '{key}' nhưng file không dùng biến này.",
            variable=key,
        )
        for key in sorted(vocabulary.required - used)
    ]


def _warn_plain_styled(
    vocabulary: _Vocabulary, declared: Iterable[str], richtext: set[str]
) -> list[TemplateDiagnostic]:
    """⭐ `COCAS-6008` — declared `render_style` but written `{{ v }}`.

    Compares against `richtext`, which came from the **text** scan: by the time
    the AST exists both spellings look identical (§12.8.2).
    """
    styled_leaves = {vocabulary.leaf_of(path) for path in richtext}
    findings = []
    for path in sorted(declared):
        leaf = vocabulary.leaf_of(path)
        if leaf in vocabulary.styled and leaf not in styled_leaves:
            findings.append(
                TemplateDiagnostic(
                    code="COCAS-6008",
                    severity=DiagnosticSeverity.WARNING,
                    message=(
                        f"Biến '{leaf}' cần in đậm. "
                        f"Sửa `{{{{ {leaf} }}}}` thành `{{{{r {leaf} }}}}`."
                    ),
                    variable=leaf,
                )
            )
    return findings


def _warn_non_iterable(
    loop_roots: Iterable[str], vocabulary: _Vocabulary
) -> list[TemplateDiagnostic]:
    """⭐ `COCAS-6012` — in v1.0 (`min = max = 1`) no known variable is a list.

    Only fires for variables that *are* known: an unrecognised name already
    got `COCAS-6009`, and one mistake should not produce two warnings.
    """
    return [
        TemplateDiagnostic(
            code="COCAS-6012",
            severity=DiagnosticSeverity.WARNING,
            message=f"Biến '{path}' không lặp được.",
            variable=path,
        )
        for path in sorted(set(loop_roots))
        if vocabulary.is_known(path)
    ]


def _scan_docxtpl_markers(text: str, part_name: str) -> list[TemplateDiagnostic]:
    """`COCAS-6010` — v1.0 renders no images, so a `{%p %}`/`{{p }}` stays blank."""
    findings = []
    for paragraph, line in enumerate(text.splitlines()):
        if _IMAGE_TAG_RE.search(line):
            findings.append(
                TemplateDiagnostic(
                    code="COCAS-6010",
                    severity=DiagnosticSeverity.WARNING,
                    message=(
                        "Hệ thống không nhúng ảnh vào hợp đồng. "
                        "Placeholder này sẽ bị bỏ trống."
                    ),
                    paragraph=paragraph,
                    part=part_name,
                )
            )
    return findings


def _warn_party_schema(
    party_schema: Sequence[Mapping[str, object]],
) -> list[TemplateDiagnostic]:
    """⭐ `COCAS-6016` — exactly the three v1.0 limits listed in §4.5.

    ⚠️ Deliberately does **not** reject a schema with more than one party:
    §4.5's limit table has three entries and multi-party trees are what
    `RenderContextBuilder` §12.9 step 2 exists for. Adding a fourth rejection
    reason here would block templates the rest of the design supports.
    """
    reasons: list[str] = []
    for party in party_schema:
        key = party.get("key") or "?"
        entity_type = party.get("entity_type")
        if entity_type is not None and entity_type != "INDIVIDUAL":
            reasons.append(f"bên '{key}' khai entity_type={entity_type}")
        for bound in ("min", "max"):
            value = party.get(bound)
            if value is not None and value != 1:
                reasons.append(f"bên '{key}' khai {bound}={value}")
        collect = party.get("collect")
        if isinstance(collect, Sequence) and not isinstance(collect, str | bytes):
            extra = [c for c in collect if c not in ("contact", "bank_account")]
            if extra:
                reasons.append(f"bên '{key}' khai collect={extra}")
    if not reasons:
        return []
    return [
        TemplateDiagnostic(
            code="COCAS-6016",
            severity=DiagnosticSeverity.ERROR,
            message=(
                "Mẫu hợp đồng dành cho tổ chức / nhiều bên chưa được hỗ trợ ở "
                f"phiên bản này ({'; '.join(reasons)})."
            ),
        )
    ]


def _errors_first(diagnostics: Iterable[TemplateDiagnostic]) -> tuple[TemplateDiagnostic, ...]:
    """Errors before warnings, otherwise stable — the UI shows blockers first."""
    items = list(diagnostics)
    return tuple(
        [d for d in items if d.severity is DiagnosticSeverity.ERROR]
        + [d for d in items if d.severity is DiagnosticSeverity.WARNING]
    )
