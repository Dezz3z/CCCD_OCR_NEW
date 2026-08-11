"""Measure `DocxTemplateInspector` (Port 20) against real `.docx` templates.

Usage:
    python backend/scripts/verify_template_inspection.py "<thư mục chứa .docx>"

Prints, per file: status, variable classification, rich-text markers and every
diagnostic — then a summary table. It also runs the ⭐ SSTI battery from
§9.9.1 against synthesised documents, because the two real templates cannot
prove a rejection ever happens.

⚠️ Set `$env:LOGURU_LEVEL="WARNING"` first, or the per-file log lines bury the
tables (same caveat as the other `verify_*.py` scripts).
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

from docx import Document

from cocas.domain.exceptions import NotADocxFileError, TemplateSyntaxError
from cocas.domain.ports.templates import TemplateInspection
from cocas.infrastructure.documents.template_inspector import DocxTemplateInspector

# §4.5 — the declaration of the real `01A_GDKQ` template.
GDKQ_PARTY_SCHEMA: list[dict[str, object]] = [
    {
        "key": "holder",
        "label": "Khách hàng",
        "entity_type": "INDIVIDUAL",
        "required": True,
        "min": 1,
        "max": 1,
        "is_primary": True,
        "collect": ["contact"],
        "extra_fields": [
            {
                "key": "securities_account_no",
                "label": "Số tài khoản chứng khoán",
                "type": "securities_account",
                "required": True,
                "render_style": {"bold": True},
            }
        ],
    }
]

GDN_PARTY_SCHEMA: list[dict[str, object]] = [
    {
        "key": "holder",
        "label": "Khách hàng",
        "entity_type": "INDIVIDUAL",
        "required": True,
        "min": 1,
        "max": 1,
        "is_primary": True,
        "collect": ["contact", "bank_account"],
        "extra_fields": [],
    }
]

SCHEMAS: dict[str, list[dict[str, object]]] = {
    "01A_HD_GDKQ.docx": GDKQ_PARTY_SCHEMA,
    "01A_HD_GDN.docx": GDN_PARTY_SCHEMA,
}

# ⭐ §9.9.1 — every one of these parses cleanly, so the parser cannot be the gate.
SSTI_PAYLOADS = [
    "{{ ''.__class__.__mro__[1].__subclasses__() }}",
    "{{ config.items() }}",
    "{{ lipsum.__globals__['os'].popen('calc').read() }}",
    "{{ self._TemplateReference__context }}",
    "{{ namespace() }}",
    "{{ ''['__class__'] }}",
    "{% include 'other.docx' %}",
    "{% extends 'base.docx' %}",
    "{% import 'macros.docx' as m %}",
    "{{ full_name|attr('__class__') }}",
    "{{ cycler(1, 2) }}",
    "{{ range(10) }}",
]

SAFE_TEMPLATES = [
    "Ho ten: {{ full_name }}",
    "Ho ten: {{ full_name|upper }} sinh ngay {{ dob }}",
    "So TK: {{r securities_account_no }}",
    "{{ holder.full_name }} — {{ holder.address }}",
]


def _make_docx(paragraphs: list[str]) -> bytes:
    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def _report(name: str, inspection: TemplateInspection) -> None:
    print(f"\n  {name}")
    print(f"      status        : {inspection.status.value}")
    print(f"      declared ({len(inspection.declared):2d}) : {', '.join(inspection.declared)}")
    print(f"      required      : {', '.join(inspection.required) or '—'}")
    print(f"      optional      : {', '.join(inspection.optional) or '—'}")
    print(f"      unknown       : {', '.join(inspection.unknown) or '—'}")
    print(f"      richtext      : {', '.join(inspection.richtext_vars) or '—'}")
    print(f"      loops / ifs   : {inspection.has_loops} / {inspection.has_conditionals}")
    if inspection.diagnostics:
        print("      diagnostics   :")
        for diagnostic in inspection.diagnostics:
            where = f" [{diagnostic.part} đoạn {diagnostic.paragraph}]" if diagnostic.part else ""
            print(f"        {diagnostic.severity.value:7} {diagnostic.code}{where}"
                  f"  {diagnostic.message}")
    else:
        print("      diagnostics   : (không có)")


def _measure_real_templates(folder: Path, inspector: DocxTemplateInspector) -> list[bool]:
    print("=" * 78)
    print(f"MẪU THẬT — {folder}")
    print("=" * 78)
    outcomes: list[bool] = []
    for path in sorted(folder.glob("*.docx")):
        schema = SCHEMAS.get(path.name, GDN_PARTY_SCHEMA)
        try:
            inspection = inspector.inspect(path.read_bytes(), schema)
        except (NotADocxFileError, TemplateSyntaxError) as exc:
            print(f"\n  {path.name}\n      TỪ CHỐI: {type(exc).__name__}: {exc}")
            outcomes.append(False)
            continue
        _report(path.name, inspection)
        outcomes.append(inspection.is_registrable)
    return outcomes


def _measure_ssti(inspector: DocxTemplateInspector) -> tuple[int, int]:
    print()
    print("=" * 78)
    print("SSTI — mỗi payload PHẢI bị từ chối (COCAS-6014)")
    print("=" * 78)
    blocked = 0
    for payload in SSTI_PAYLOADS:
        inspection = inspector.inspect(_make_docx([payload]), GDN_PARTY_SCHEMA)
        codes = {d.code for d in inspection.errors}
        ok = "COCAS-6014" in codes
        blocked += ok
        print(f"  {'CHẶN ' if ok else '❌LỌT'} {payload}")
        if not ok:
            print(f"        -> status={inspection.status.value} diagnostics={codes}")
    return blocked, len(SSTI_PAYLOADS)


def _measure_safe(inspector: DocxTemplateInspector) -> tuple[int, int]:
    print()
    print("=" * 78)
    print("ĐỐI CHỨNG — mẫu sạch PHẢI KHÔNG bị từ chối")
    print("=" * 78)
    passed = 0
    for body in SAFE_TEMPLATES:
        inspection = inspector.inspect(_make_docx([body]), GDKQ_PARTY_SCHEMA)
        ok = inspection.is_registrable
        passed += ok
        codes = ", ".join(sorted({d.code for d in inspection.diagnostics})) or "—"
        print(f"  {'OK   ' if ok else '❌TỪ CHỐI'} {body}")
        print(f"        status={inspection.status.value} diagnostics={codes}")
    return passed, len(SAFE_TEMPLATES)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    folder = Path(sys.argv[1])
    if not folder.is_dir():
        print(f"Không thấy thư mục: {folder}")
        return 2

    inspector = DocxTemplateInspector()
    real = _measure_real_templates(folder, inspector)
    blocked, total_payloads = _measure_ssti(inspector)
    safe_ok, total_safe = _measure_safe(inspector)

    print()
    print("=" * 78)
    print("TỔNG KẾT")
    print("=" * 78)
    print(f"  Mẫu thật đăng ký được : {sum(real)}/{len(real)}")
    print(f"  SSTI bị chặn          : {blocked}/{total_payloads}")
    print(f"  Mẫu sạch không bị chặn: {safe_ok}/{total_safe}")
    ok = all(real) and blocked == total_payloads and safe_ok == total_safe
    print(f"  => {'ĐẠT' if ok else 'CHƯA ĐẠT'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
