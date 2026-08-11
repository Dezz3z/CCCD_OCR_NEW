"""Measure the module-4 chain end to end on the two REAL `.docx` templates.

Usage:
    python backend/scripts/verify_docx_render.py "<thư mục chứa .docx>"

Runs `RenderContextBuilder` → `DocxContextAdapter` → `DocxRenderer` with a
realistic customer, then checks four things that no unit test can:

  1. ⭐ **Equivalence with `docxtpl` itself** — the same concatenated `<w:t>`
     text and the same set of bold runs. This is the only evidence that
     bypassing `render()`/`save()` (§9.12.1) did not change the document.
  2. Timing, cold and warm, against the 800 ms budget of NFR-03.
  3. No `{{`, no `None`, no `StyledValue` anywhere in the output.
  4. ⭐ The securities account number is a **bold run**, not bold-looking text.

⚠️ Set `$env:LOGURU_LEVEL="WARNING"` first, like the other `verify_*.py`.
⚠️ The docxtpl reference render takes 14–34 s per template — that is the
   measurement, not a hang. Pass `--skip-reference` to leave it out.
"""
from __future__ import annotations

import sys
import time
import uuid
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

from docxtpl import DocxTemplate
from jinja2 import Undefined
from jinja2.sandbox import SandboxedEnvironment
from lxml import etree

from cocas.application.dto.contract import ContractDraft, PartyDraft
from cocas.application.render_context_builder import RenderContextBuilder
from cocas.domain.entities.bank_account import BankAccount
from cocas.domain.entities.customer import Customer
from cocas.domain.entities.template import Template
from cocas.domain.enums.data_quality import DataQuality
from cocas.domain.enums.gender import Gender
from cocas.domain.value_objects.bank_account_number import BankAccountNumber
from cocas.domain.value_objects.citizen_id import CitizenId
from cocas.domain.value_objects.email_address import EmailAddress
from cocas.domain.value_objects.id_card_dates import IdCardDates
from cocas.domain.value_objects.issue_place import CUC_CANH_SAT_QLHC_TTXH, IssuePlace
from cocas.domain.value_objects.person_name import PersonName
from cocas.domain.value_objects.securities_account_number import SecuritiesAccountNumber
from cocas.domain.value_objects.vietnamese_phone import VietnamesePhone
from cocas.infrastructure.documents.docx_context_adapter import DocxContextAdapter
from cocas.infrastructure.documents.docx_renderer import DocxRenderer

NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
BUDGET_MS = 800
WARM_RUNS = 20
NOW = datetime(2026, 8, 11, 9, 0, tzinfo=UTC)
STK = "008C123456"


def _customer() -> Customer:
    return Customer(
        id=uuid.uuid4(),
        created_by="nvnghiep",
        full_name=PersonName.from_raw("NGUYỄN VĂN AN"),
        id_number=CitizenId.from_raw("001199012345"),
        date_of_birth=date(1990, 5, 14),
        issue_place=IssuePlace(CUC_CANH_SAT_QLHC_TTXH),
        id_card_dates=IdCardDates(issue_date=date(2021, 8, 20), expiry_date=date(2030, 5, 14)),
        phone=VietnamesePhone.from_raw("0912345678"),
        email=EmailAddress.from_raw("an.nguyen@example.com"),
        address="123 Trần Hưng Đạo, Hoàn Kiếm, Hà Nội",
        data_quality=DataQuality.OCR_VERIFIED,
        created_at=NOW,
        gender=Gender.NAM,
        securities_account_no=SecuritiesAccountNumber.from_raw(STK),
    )


def _template(code: str, collect: list[str], extras: list[dict[str, object]]) -> Template:
    return Template(
        id=uuid.uuid4(),
        code=code,
        name=code,
        party_schema=[
            {
                "key": "holder",
                "label": "Khách hàng",
                "entity_type": "INDIVIDUAL",
                "min": 1,
                "max": 1,
                "is_primary": True,
                "collect": collect,
                "extra_fields": extras,
            }
        ],
        contract_no_pattern="01A-{yyyymm}-{seq:05d}",
        export_name_pattern="Mẫu 01A - {full_name}",
        created_at=NOW,
        suppressed_variables=["contract_date", "contract_date_text", "day", "month", "year"],
    )


TEMPLATES = {
    "01A_HD_GDKQ.docx": _template(
        "01A_GDKQ",
        ["contact"],
        [
            {
                "key": "securities_account_no",
                "label": "Số tài khoản chứng khoán",
                "type": "securities_account",
                "required": True,
                "render_style": {"bold": True},
            }
        ],
    ),
    "01A_HD_GDN.docx": _template("01A_HD_GDN", ["contact", "bank_account"], []),
}


class _Empty(Undefined):
    def __str__(self) -> str:
        return ""


def _all_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    return "".join(node.text or "" for node in root.iter(f"{NS}t"))


def _bold(path: Path) -> set[str]:
    with zipfile.ZipFile(path) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    found = set()
    for run in root.iter(f"{NS}r"):
        properties = run.find(f"{NS}rPr")
        if properties is not None and properties.find(f"{NS}b") is not None:
            text = "".join(node.text or "" for node in run.iter(f"{NS}t")).strip()
            if text:
                found.add(text)
    return found


def _reference_render(source: Path, context: dict[str, object], out: Path) -> float:
    """docxtpl's own path — the thing we must produce the same document as."""
    started = time.perf_counter()
    template = DocxTemplate(source)
    template.render(dict(context), jinja_env=SandboxedEnvironment(undefined=_Empty))
    template.save(out)
    return (time.perf_counter() - started) * 1000


def _measure(folder: Path, out_dir: Path, *, reference: bool) -> bool:
    builder, adapter, renderer = RenderContextBuilder(), DocxContextAdapter(), DocxRenderer()
    customer = _customer()
    bank = BankAccount(
        id=uuid.uuid4(),
        customer_id=customer.id,
        account_number=BankAccountNumber.from_raw("1234567890"),
        bank_name="Ngân hàng TMCP Ngoại thương Việt Nam",
        branch="Chi nhánh Hà Nội",
        created_at=NOW,
        bank_code="VCB",
    )
    draft = ContractDraft(
        contract_no="01A-GDN-202608-00042",
        created_by_name="nvnghiep",
        today=date(2026, 8, 11),
        parties=(PartyDraft("holder", customer, bank, {"securities_account_no": STK}),),
    )

    # ⚠️ ⭐ **Timing first, for every template, before any reference render.**
    # An earlier version interleaved them and the p95 verdict flipped between
    # templates from run to run: whichever template was measured *second*
    # failed, because a 37 s `docxtpl` render and a second cold prepare had
    # just churned memory on a 4 GB box. Measured cleanly, both templates sit
    # at p95 463–634 ms. The instrument was the problem, again.
    timings: dict[str, tuple[float, list[int]]] = {}
    for name, template in TEMPLATES.items():
        source = folder / name
        if not source.exists():
            continue
        adapted = adapter.adapt(builder.build(draft, template))
        isolated = DocxRenderer()
        cold_started = time.perf_counter()
        isolated.render(str(source), adapted, str(out_dir / f"out_{name}"))
        cold_ms = (time.perf_counter() - cold_started) * 1000
        timings[name] = (
            cold_ms,
            sorted(
                isolated.render(
                    str(source), adapter.adapt(builder.build(draft, template)),
                    str(out_dir / f"out_{name}"),
                ).duration_ms
                for _ in range(WARM_RUNS)
            ),
        )

    verdicts: list[bool] = []
    for name, template in TEMPLATES.items():
        source = folder / name
        if not source.exists():
            print(f"\n  ⚠️ Không thấy {name} — bỏ qua")
            continue
        print(f"\n{'=' * 78}\n{name}\n{'=' * 78}")

        context = builder.build(draft, template)
        adapted = adapter.adapt(context)
        cold_ms, warm = timings[name]
        result = renderer.render(str(source), adapted, str(out_dir / f"out_{name}"))
        p50, p95 = warm[len(warm) // 2], warm[int(len(warm) * 0.95) - 1]

        print(f"  biến trong ngữ cảnh : {len(context)}")
        print(f"  lần đầu (chuẩn bị)  : {cold_ms:.0f} ms")
        print(f"  warm ({WARM_RUNS} lần)      : p50 {p50} · p95 {p95} · max {warm[-1]} ms "
              f"(ngân sách p95 ≤ {BUDGET_MS} ms)")
        print(f"  kích thước / sha256 : {result.size_bytes:,} B / {result.sha256.hex()[:16]}…")

        produced = out_dir / f"out_{name}"
        text, bold = _all_text(produced), _bold(produced)
        checks: list[tuple[str, bool]] = [
            ("họ tên đã thay", "NGUYỄN VĂN AN" in text),
            ("số CCCD đã thay", "001199012345" in text),
            ("không còn '{{'", "{{" not in text),
            ("không in ra 'None'", "None" not in text),
            ("không lộ 'StyledValue'", "StyledValue" not in text),
            (f"p95 ≤ {BUDGET_MS} ms (NFR-03)", p95 <= BUDGET_MS),
        ]
        if template.code == "01A_GDKQ":
            checks.append(("⭐ STK chứng khoán IN ĐẬM", any(STK in b for b in bold)))

        if reference:
            reference_path = out_dir / f"ref_{name}"
            reference_ms = _reference_render(source, adapted, reference_path)
            same_text = text == _all_text(reference_path)
            same_bold = bold == _bold(reference_path)
            speedup = reference_ms / max(p50, 1)
            print(f"  docxtpl đối chứng   : {reference_ms:.0f} ms  → nhanh hơn {speedup:.0f} lan")
            checks.append(("⭐ văn bản khớp docxtpl", same_text))
            checks.append(("⭐ tập in đậm khớp docxtpl", same_bold))

        for label, ok in checks:
            print(f"    {'OK  ' if ok else '❌FAIL'} {label}")
        verdicts.append(all(ok for _, ok in checks))

    return bool(verdicts) and all(verdicts)


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    folder = Path(args[0])
    if not folder.is_dir():
        print(f"Không thấy thư mục: {folder}")
        return 2

    out_dir = folder.parent / "_render_out"
    out_dir.mkdir(exist_ok=True)
    ok = _measure(folder, out_dir, reference="--skip-reference" not in sys.argv)

    print(f"\n{'=' * 78}\nTỔNG KẾT: {'ĐẠT' if ok else 'CHƯA ĐẠT'}   (đầu ra: {out_dir})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
