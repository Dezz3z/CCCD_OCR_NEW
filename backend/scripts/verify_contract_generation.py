"""Measure `GenerateContractUseCase` end to end on the two REAL templates.

Usage:
    python backend/scripts/verify_contract_generation.py "<thư mục chứa .docx>"

Unlike `verify_docx_render.py`, which measures the renderer, this drives the
whole of §9.11 — validation, contract numbering, export naming, the two
transactions, and the encrypted Vault write — with a real
`EncryptedFileVault` on a temporary directory. Only the database is faked,
because the portable cluster on 55432 is not running.

What it checks that no unit test can:

  1. ⭐ **No plaintext `.docx` anywhere on disk** — the §12.11.2 invariant,
     verified by walking the entire temp tree, not by trusting the call.
  2. Timing of the whole use case against §9.11's "201 sau ~500 ms".
  3. The bytes in the Vault open as a real `.docx` with `python-docx`, and
     the contract number / customer name actually appear in the text.
  4. ⭐ `contract_document.file_sha256` matches the **plaintext**, and does
     not match the ciphertext on disk (§9.15).
  5. The §9.16 failure path: a broken render leaves `GENERATION_FAILED` and
     no orphan file.

⚠️ Set `$env:LOGURU_LEVEL="WARNING"` first, like the other `verify_*.py`.
⚠️ ⭐ **Every timing is collected before any heavy verification**, and each
   template gets a fresh `DocxRenderer`. Interleaving the two is what made
   `verify_docx_render.py` report a different failing template on two
   identical runs (denominator trap, 4th occurrence).
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import shutil
import statistics
import sys
import tempfile
import time
import uuid
import zipfile
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from types import TracebackType

from docx import Document

from cocas.application.dto.contract import GenerateContractCommand, PartyRequest
from cocas.application.render_context_builder import RenderContextBuilder
from cocas.application.use_cases.contract.generate_contract import GenerateContractUseCase
from cocas.domain.entities.bank_account import BankAccount
from cocas.domain.entities.contract import Contract
from cocas.domain.entities.customer import Customer
from cocas.domain.entities.template import Template
from cocas.domain.entities.template_version import TemplateVersion
from cocas.domain.enums.contract_status import ContractStatus
from cocas.domain.enums.data_quality import DataQuality
from cocas.domain.enums.gender import Gender
from cocas.domain.enums.template_validation_status import TemplateValidationStatus
from cocas.domain.exceptions import RenderError
from cocas.domain.ports.storage import VaultCategory, VaultRef
from cocas.domain.services.contract_number_generator import ContractNumberGenerator
from cocas.domain.services.export_name_generator import ExportNameGenerator
from cocas.domain.validation.engine import ValidationEngine
from cocas.domain.value_objects.bank_account_number import BankAccountNumber
from cocas.domain.value_objects.citizen_id import CitizenId
from cocas.domain.value_objects.email_address import EmailAddress
from cocas.domain.value_objects.id_card_dates import IdCardDates
from cocas.domain.value_objects.issue_place import CUC_CANH_SAT_QLHC_TTXH, IssuePlace
from cocas.domain.value_objects.person_name import PersonName
from cocas.domain.value_objects.vietnamese_phone import VietnamesePhone
from cocas.infrastructure.documents.docx_context_adapter import DocxContextAdapter
from cocas.infrastructure.documents.docx_renderer import DocxRenderer
from cocas.infrastructure.storage.encrypted_file_vault import EncryptedFileVault

NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
BUDGET_MS = 800
WARM_RUNS = 15
NOW = datetime(2026, 8, 11, 9, 0, tzinfo=UTC)
TODAY = date(2026, 8, 11)
STK = "008C123456"

TEMPLATES: dict[str, dict[str, object]] = {
    "01A_HD_GDN.docx": {
        "code": "01A_HD_GDN",
        "name": "Mẫu số 01A/HĐ-GĐN",
        "collect": ["contact", "bank_account"],
        "extra_fields": [],
        "contract_no_pattern": "01A-GDN-{yyyy}{MM}-{seq:05d}",
        "export_name_pattern": "Mẫu 01A - {full_name}",
    },
    "01A_HD_GDKQ.docx": {
        "code": "01A_GDKQ",
        "name": "Mẫu 01A/GDKQ",
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
        "contract_no_pattern": "01A-KQ-{yyyy}{MM}-{seq:05d}",
        "export_name_pattern": "01A_GDKQ - {full_name}",
    },
}


# --------------------------------------------------------------- fake database


class _Store:
    def __init__(self, rows: dict[uuid.UUID, object] | None = None) -> None:
        self.rows: dict[uuid.UUID, object] = dict(rows or {})

    async def get(self, entity_id: object) -> object | None:
        return self.rows.get(entity_id)  # type: ignore[arg-type]

    async def add(self, entity: object) -> None:
        self.rows[entity.id] = entity  # type: ignore[attr-defined]

    async def update(
        self,
        entity: object,
        expected_version: int | None = None,  # noqa: ARG002 - protocol signature
    ) -> None:
        self.rows[entity.id] = entity  # type: ignore[attr-defined]


class _TemplateStore(_Store):
    async def get_for_update(self, template_id: uuid.UUID) -> object | None:
        return self.rows.get(template_id)


class _ContractStore(_Store):
    def __init__(self) -> None:
        super().__init__()
        self.snapshots: list[dict[str, object]] = []

    def stage_snapshot(self, snapshot: dict[str, object]) -> None:
        self.snapshots.append(snapshot)


class FakeUow:
    def __init__(self, template: Template, version: TemplateVersion) -> None:
        self.templates = _TemplateStore({template.id: template})
        self.template_versions = _Store({version.id: version})
        self.customers = _Store()
        self.bank_accounts = _Store()
        self.contracts = _ContractStore()
        self.contract_parties = _Store()
        self.contract_documents = _Store()

    def __call__(self) -> FakeUow:
        return self

    async def __aenter__(self) -> FakeUow:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        return None


class _Clock:
    def now(self) -> datetime:
        return NOW

    def today(self) -> date:
        return TODAY


class _Ids:
    def new_id(self) -> uuid.UUID:
        return uuid.uuid4()


# ---------------------------------------------------------------- test fixtures


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
    )


def _bank(customer_id: uuid.UUID) -> BankAccount:
    return BankAccount(
        id=uuid.uuid4(),
        customer_id=customer_id,
        account_number=BankAccountNumber.from_raw("1234567890"),
        bank_name="Ngân hàng TMCP Ngoại thương Việt Nam",
        branch="Chi nhánh Hà Nội",
        created_at=NOW,
        bank_code="VCB",
    )


def _template(spec: dict[str, object]) -> Template:
    return Template(
        id=uuid.uuid4(),
        code=str(spec["code"]),
        name=str(spec["name"]),
        party_schema=[
            {
                "key": "holder",
                "label": "Khách hàng",
                "entity_type": "INDIVIDUAL",
                "min": 1,
                "max": 1,
                "is_primary": True,
                "collect": spec["collect"],
                "extra_fields": spec["extra_fields"],
            }
        ],
        contract_no_pattern=str(spec["contract_no_pattern"]),
        export_name_pattern=str(spec["export_name_pattern"]),
        created_at=NOW,
        suppressed_variables=[
            "contract_date",
            "contract_date_text",
            "day",
            "month",
            "year",
        ],
        contract_no_seq=41,
    )


def _version(template: Template, relative: str, sha256: bytes, size: int) -> TemplateVersion:
    version = TemplateVersion(
        id=uuid.uuid4(),
        template_id=template.id,
        version_no=1,
        file_path=relative,
        file_sha256=sha256,
        file_size_bytes=size,
        original_filename=Path(relative).name,
        declared_variables=["full_name", "id_number", "contract_date"],
        required_variables=["full_name", "id_number", "contract_date"],
        optional_variables=[],
        validation_status=TemplateValidationStatus.VALID,
        created_by="nvnghiep",
        created_at=NOW,
    )
    template.active_version_id = version.id
    return version


class Rig:
    """One template, wired for generation, with a fresh renderer and Vault."""

    def __init__(self, source: Path, workspace: Path, spec: dict[str, object]) -> None:
        self.spec = spec
        self.templates_dir = workspace / "templates"
        relative = f"{spec['code']}/v1.docx"
        destination = self.templates_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        data = destination.read_bytes()

        self.template = _template(spec)
        self.version = _version(
            self.template, relative, hashlib.sha256(data).digest(), len(data)
        )
        self.uow = FakeUow(self.template, self.version)
        self.customer = _customer()
        self.bank = _bank(self.customer.id)
        self.uow.customers.rows[self.customer.id] = self.customer
        self.uow.bank_accounts.rows[self.bank.id] = self.bank

        self.vault_root = workspace / "vault"
        self.storage = EncryptedFileVault(
            root=self.vault_root,
            vault_key=b"\x2a" * 32,
            clock=_Clock(),
            id_generator=_Ids(),
        )
        # ⭐ A fresh renderer per rig: a shared cache would make whichever
        # template ran second look faster for a reason that is not about it.
        self.renderer = DocxRenderer()
        self.use_case = GenerateContractUseCase(
            uow_factory=self.uow,
            context_builder=RenderContextBuilder(),
            context_adapter=DocxContextAdapter(),
            renderer=self.renderer,
            file_storage=self.storage,
            validator=ValidationEngine(),
            contract_numbers=ContractNumberGenerator(),
            export_names=ExportNameGenerator(),
            templates_dir=self.templates_dir,
            clock=_Clock(),
            id_generator=_Ids(),
        )

    def command(self) -> GenerateContractCommand:
        wants_stk = bool(self.spec["extra_fields"])
        return GenerateContractCommand(
            template_id=self.template.id,
            parties=[
                PartyRequest(
                    party_key="holder",
                    customer_id=self.customer.id,
                    bank_account_id=None if wants_stk else self.bank.id,
                    party_extra={"securities_account_no": STK} if wants_stk else {},
                )
            ],
            created_by="nvnghiep",
            created_by_name="Nguyễn Văn Nghiệp",
        )


# ------------------------------------------------------------------ inspection


def _document_text(blob: bytes) -> str:
    """Concatenated `<w:t>` — ⚠️ never `python-docx .paragraphs`, which drops
    table content and repeats merged cells (§9.18)."""
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    from lxml import etree

    root = etree.fromstring(xml.encode("utf-8"))
    return "".join(node.text or "" for node in root.iter(f"{NS}t"))


def _bold_runs(blob: bytes) -> set[str]:
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    from lxml import etree

    root = etree.fromstring(xml.encode("utf-8"))
    found: set[str] = set()
    for run in root.iter(f"{NS}r"):
        properties = run.find(f"{NS}rPr")
        if properties is None or properties.find(f"{NS}b") is None:
            continue
        text = "".join(node.text or "" for node in run.iter(f"{NS}t")).strip()
        if text:
            found.add(text)
    return found


_INSPECTIONS: dict[Path, tuple[str, ...]] = {}


def _declared(path: Path) -> tuple[str, ...]:
    """The variables the template really uses, straight from Port 20."""
    if path not in _INSPECTIONS:
        from cocas.infrastructure.documents.template_inspector import (
            DocxTemplateInspector,
        )

        inspection = DocxTemplateInspector().inspect(
            path.read_bytes(), party_schema=[], contract_fields=[]
        )
        _INSPECTIONS[path] = inspection.declared
    return _INSPECTIONS[path]


def _declared_count(path: Path) -> str:
    return f"{len(_declared(path))} biến"


def _unfilled(
    path: Path, snapshot: dict[str, object], suppressed: Sequence[str], text: str
) -> list[str]:
    """Declared variables whose rendered value never made it into the page."""
    blanked = set(suppressed)
    missing: list[str] = []
    for key in _declared(path):
        if key in blanked:
            continue
        value = str(snapshot.get(key, "")).strip()
        if value and value not in text:
            missing.append(key)
    return missing


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(int(len(ordered) * fraction), len(ordered) - 1)
    return ordered[index]


# ------------------------------------------------------------------------ main


async def _time_one(rig: Rig) -> tuple[float, list[float], object]:
    """Cold run, then `WARM_RUNS` warm ones. Nothing heavy in between."""
    started = time.perf_counter()
    result = await rig.use_case.execute(rig.command())
    cold_ms = (time.perf_counter() - started) * 1000

    warm: list[float] = []
    for _ in range(WARM_RUNS):
        started = time.perf_counter()
        await rig.use_case.execute(rig.command())
        warm.append((time.perf_counter() - started) * 1000)
    return cold_ms, warm, result


async def _failure_path(source: Path, workspace: Path, spec: dict[str, object]) -> list[str]:
    """§9.16 — a render that fails must leave a durable `GENERATION_FAILED`."""
    rig = Rig(source, workspace / "failure", spec)

    class Broken:
        def render_to_bytes(self, *args: object, **kwargs: object) -> object:  # noqa: ARG002
            raise RenderError("Lỗi trong mẫu hợp đồng tại '{{full_name}}'.")

        def render(self, *args: object, **kwargs: object) -> object:  # noqa: ARG002
            raise RenderError("unused")

    rig.use_case._renderer = Broken()  # type: ignore[assignment]

    problems: list[str] = []
    try:
        await rig.use_case.execute(rig.command())
        problems.append("render hỏng nhưng use case vẫn báo thành công")
    except RenderError:
        pass

    contracts = list(rig.uow.contracts.rows.values())
    if len(contracts) != 1:
        problems.append(f"kỳ vọng 1 dòng contract, có {len(contracts)}")
    else:
        contract = contracts[0]
        assert isinstance(contract, Contract)
        if contract.status is not ContractStatus.GENERATION_FAILED:
            problems.append(f"trạng thái là {contract.status.value}, không phải GENERATION_FAILED")
    if rig.uow.contract_documents.rows:
        problems.append("có dòng contract_document cho một lần render hỏng")
    orphans = list(rig.vault_root.rglob("*.enc")) if rig.vault_root.exists() else []
    if orphans:
        problems.append(f"còn {len(orphans)} file .enc mồ côi")
    return problems


async def main(folder: Path) -> int:
    available = [name for name in TEMPLATES if (folder / name).is_file()]
    if not available:
        print(f"❌ Không tìm thấy mẫu nào trong {folder}")
        print(f"   Cần một trong: {', '.join(TEMPLATES)}")
        return 2

    workspace = Path(tempfile.mkdtemp(prefix="cocas-verify-contract-"))
    try:
        # ⭐ Phase 1 — every timing first, nothing heavy interleaved.
        rigs = {name: Rig(folder / name, workspace / name, TEMPLATES[name]) for name in available}
        timings = {name: await _time_one(rig) for name, rig in rigs.items()}

        # Phase 2 — correctness, now that no clock is running.
        failed = False
        for name in available:
            rig = rigs[name]
            cold_ms, warm, result = timings[name]
            p50 = statistics.median(warm)
            p95 = _percentile(warm, 0.95)

            print(f"\n{'=' * 74}\n{name}  ({rig.spec['code']})\n{'=' * 74}")
            print(f"  contract_no        {result.contract_no}")
            print(f"  export_name        {result.export_name}")
            print(f"  vault_path         {result.vault_path}")
            print(f"  file_size_bytes    {result.file_size_bytes:,}")
            print(
                f"  ⏱  nguội {cold_ms:8.0f} ms   ấm p50 {p50:6.0f} · "
                f"p95 {p95:6.0f} · max {max(warm):6.0f} ms  (ngân sách {BUDGET_MS} ms)"
            )
            if p95 > BUDGET_MS:
                print(f"  ❌ p95 vượt ngân sách {BUDGET_MS} ms")
                failed = True
            else:
                print("  ✅ p95 trong ngân sách")

            blob = rig.storage.load(
                VaultRef(VaultCategory.CONTRACT_DOCUMENT, result.vault_path)
            )
            ciphertext = (rig.vault_root / result.vault_path).read_bytes()

            checks: list[tuple[str, bool, str]] = []
            checks.append(
                ("mở được bằng python-docx", _opens(blob), "zip không phải .docx hợp lệ")
            )
            text = _document_text(blob)
            checks.append(("có tên khách hàng", "NGUYỄN VĂN AN" in text, "thiếu tên"))

            # ⚠️ NOT `contract_no in text`. Measured 2026-08-11: **neither real
            # template uses `{{contract_no}}`** — it is an internal identifier
            # for the audit trail and lookups (§9.14.1), not something printed
            # on the page. Asserting it would fail a correct document. What is
            # worth asserting instead is that every variable the template
            # *does* declare came out filled.
            snapshot = rig.uow.contracts.snapshots[0]
            missing = _unfilled(folder / name, snapshot, rig.template.suppressed_variables, text)
            checks.append(
                (
                    f"mọi biến khai báo đều có giá trị trong văn bản ({_declared_count(folder / name)})",
                    not missing,
                    f"chưa thấy: {', '.join(missing)}",
                )
            )
            checks.append(("không còn thẻ Jinja", "{{" not in text, "còn '{{' trong văn bản"))
            checks.append(("không có 'None'", "None" not in text, "có chuỗi 'None'"))
            checks.append(
                (
                    "file_sha256 = hash BẢN RÕ",
                    hashlib.sha256(blob).digest() == result.file_sha256,
                    "hash không khớp bản rõ",
                )
            )
            checks.append(
                (
                    "file_sha256 ≠ hash ciphertext",
                    hashlib.sha256(ciphertext).digest() != result.file_sha256,
                    "hash lại khớp ciphertext (§9.15)",
                )
            )
            # ⚠️ Excludes every Template Store, not just this rig's: the
            # workspace holds one per template, and a sibling's `.docx` is a
            # *template* — plaintext by design (§11) — not a leaked contract.
            plaintext_on_disk = [
                p
                for p in workspace.rglob("*.docx")
                if p.is_file() and "templates" not in p.parts
            ]
            checks.append(
                (
                    "⭐ không có .docx rõ trên đĩa",
                    not plaintext_on_disk,
                    f"tìm thấy {len(plaintext_on_disk)} file",
                )
            )
            checks.append(
                (
                    "không còn file .tmp",
                    not list(rig.vault_root.rglob("*.tmp")),
                    "còn file tạm",
                )
            )
            if rig.spec["extra_fields"]:
                checks.append(
                    ("STK chứng khoán in đậm", STK in _bold_runs(blob), f"'{STK}' không in đậm")
                )
            checks.append(
                (
                    "snapshot đã ghi (P-09)",
                    bool(rig.uow.contracts.snapshots),
                    "không có render_snapshot",
                )
            )
            contract = next(iter(rig.uow.contracts.rows.values()))
            assert isinstance(contract, Contract)
            checks.append(
                (
                    "hợp đồng ở COMPLETED",
                    contract.status is ContractStatus.COMPLETED,
                    contract.status.value,
                )
            )

            print()
            for label, ok, detail in checks:
                print(f"  {'✅' if ok else '❌'} {label}" + ("" if ok else f" — {detail}"))
                failed = failed or not ok

        # Phase 3 — the §9.16 failure path, once.
        print(f"\n{'=' * 74}\n§9.16 — đường thất bại (render hỏng)\n{'=' * 74}")
        problems = await _failure_path(
            folder / available[0], workspace, TEMPLATES[available[0]]
        )
        for problem in problems:
            print(f"  ❌ {problem}")
        if not problems:
            print("  ✅ GENERATION_FAILED bền vững · 0 dòng contract_document · 0 file mồ côi")
        failed = failed or bool(problems)

        print(f"\n{'=' * 74}")
        print("TỔNG KẾT:", "❌ CHƯA ĐẠT" if failed else "✅ ĐẠT")
        return 1 if failed else 0
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def _opens(blob: bytes) -> bool:
    try:
        Document(io.BytesIO(blob))
    except Exception:
        return False
    return True


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(asyncio.run(main(Path(sys.argv[1]))))
