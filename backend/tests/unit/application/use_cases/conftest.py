"""In-memory Unit of Work shared by the P3 module 7 Use Case tests.

⭐ One fake per *repository shape*, not one per Use Case. Each Use Case
declares its own `I…UnitOfWork` Protocol over a subset of these attributes, so
a single object satisfies all of them structurally — which is the point of
declaring those Protocols in the first place.

⚠️ This fake commits nothing and rolls nothing back; it records whether
`commit()` was called. Tests that care about transaction boundaries assert on
`commits`, and tests that care about what actually reaches PostgreSQL belong
in `tests/integration/` behind `COCAS_TEST_DATABASE_URL`.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import TracebackType
from typing import Any

import pytest

from cocas.domain.entities.bank_account import BankAccount
from cocas.domain.entities.card_image import CardImage
from cocas.domain.entities.contract import Contract
from cocas.domain.entities.contract_document import ContractDocument
from cocas.domain.entities.customer import Customer
from cocas.domain.entities.ocr_session import OcrSession
from cocas.domain.entities.template import Template
from cocas.domain.entities.template_version import TemplateVersion
from cocas.domain.enums.job_status import JobStatus
from cocas.domain.enums.job_type import JobType
from cocas.domain.ports.persistence import OcrResultSnapshot

NOW = datetime(2026, 8, 12, 9, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self, now: datetime = NOW) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def today(self) -> Any:
        return self._now.date()


class SequentialIds:
    """Deterministic ids — a test that asserts on one should not be flaky."""

    def __init__(self) -> None:
        self._n = 0

    def new_id(self) -> uuid.UUID:
        self._n += 1
        return uuid.UUID(int=self._n)


class _Store:
    def __init__(self, rows: dict[uuid.UUID, Any] | None = None) -> None:
        self.rows: dict[uuid.UUID, Any] = dict(rows or {})
        self.added: list[Any] = []
        self.updated: list[Any] = []

    async def get(self, entity_id: object) -> Any | None:
        return self.rows.get(uuid.UUID(str(entity_id)))

    async def add(self, entity: Any) -> None:
        self.rows[entity.id] = entity
        self.added.append(entity)

    async def update(self, entity: Any, expected_version: int | None = None) -> None:
        self.rows[entity.id] = entity
        self.updated.append(entity)


class FakeCardImages(_Store):
    async def find_by_sha256(self, digest: bytes) -> CardImage | None:
        return next(
            (row for row in self.rows.values() if row.sha256 == digest), None
        )


class FakeCustomers(_Store):
    async def find_by_id_number(self, id_number: str) -> Customer | None:
        return next(
            (row for row in self.rows.values() if str(row.id_number) == id_number),
            None,
        )


class FakeBankAccounts(_Store):
    async def list_for_customer(self, customer_id: uuid.UUID) -> list[BankAccount]:
        return [row for row in self.rows.values() if row.customer_id == customer_id]


class FakeContractDocuments(_Store):
    def __init__(self, rows: dict[uuid.UUID, Any] | None = None) -> None:
        super().__init__(rows)
        self.downloads: list[uuid.UUID] = []

    async def get_for_contract(
        self, contract_id: uuid.UUID
    ) -> ContractDocument | None:
        return next(
            (row for row in self.rows.values() if row.contract_id == contract_id), None
        )

    async def record_download(self, document_id: uuid.UUID, now: object) -> None:
        self.downloads.append(document_id)


class FakeTemplates(_Store):
    async def list_active(self) -> list[Template]:
        return [
            row
            for row in self.rows.values()
            if row.is_active and not row.is_deleted
        ]

    async def get_for_update(self, template_id: uuid.UUID) -> Template | None:
        return self.rows.get(template_id)


class FakeTemplateVersions(_Store):
    async def list_for_template(self, template_id: uuid.UUID) -> list[TemplateVersion]:
        return sorted(
            (r for r in self.rows.values() if r.template_id == template_id),
            key=lambda r: r.version_no,
            reverse=True,
        )


class FakeOcrResults:
    def __init__(self) -> None:
        self.by_session: dict[uuid.UUID, OcrResultSnapshot] = {}
        self.corrections: list[tuple[uuid.UUID, str]] = []

    async def get_by_session(self, session_id: uuid.UUID) -> OcrResultSnapshot | None:
        return self.by_session.get(session_id)

    async def correct_field(
        self, field_id: uuid.UUID, value: str, *, corrected: bool = True
    ) -> bool:
        self.corrections.append((field_id, value))
        return True

    async def add(self, entity: OcrResultSnapshot) -> None:
        self.by_session[uuid.UUID(str(entity.ocr_session_id))] = entity


@dataclass
class FakeJobRow:
    id: uuid.UUID
    job_type: str
    status: str
    target_id: uuid.UUID | None = None
    target_type: str | None = None
    payload: dict[str, object] | None = None
    priority: int = 100
    attempt_count: int = 0
    max_attempts: int = 3
    progress_percent: int | None = None
    progress_message: str | None = None
    error_code: str | None = None
    error_detail: str | None = None
    is_retryable_error: bool | None = None
    heartbeat_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class FakeJobs:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, FakeJobRow] = {}
        self.progress: list[tuple[uuid.UUID, int, str]] = []

    async def enqueue(
        self,
        *,
        job_id: uuid.UUID,
        job_type: JobType,
        correlation_id: str,
        now: object,
        target_id: uuid.UUID | None = None,
        target_type: str | None = None,
        payload: dict[str, object] | None = None,
        priority: int = 100,
    ) -> uuid.UUID:
        self.rows[job_id] = FakeJobRow(
            id=job_id,
            job_type=job_type.value,
            status=JobStatus.QUEUED.value,
            target_id=target_id,
            target_type=target_type,
            payload=payload,
            priority=priority,
        )
        return job_id

    async def get(self, job_id: uuid.UUID) -> FakeJobRow | None:
        return self.rows.get(job_id)

    async def claim_next(self, now: datetime) -> FakeJobRow | None:
        row = next(
            (r for r in self.rows.values() if r.status == JobStatus.QUEUED.value), None
        )
        if row is None:
            return None
        row.status = JobStatus.RUNNING.value
        row.attempt_count += 1
        row.started_at = now
        row.heartbeat_at = now
        return row

    async def report_progress(
        self, job_id: uuid.UUID, percent: int, message: str, now: object
    ) -> None:
        self.progress.append((job_id, percent, message))

    async def finish(
        self,
        job_id: uuid.UUID,
        *,
        status: JobStatus,
        now: datetime,
        error_code: str | None = None,
        error_detail: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        row = self.rows.get(job_id)
        if row is None:
            return
        row.status = status.value
        row.finished_at = now
        row.error_code = error_code
        row.error_detail = error_detail
        row.is_retryable_error = retryable

    async def requeue_stale(self, older_than: datetime, now: datetime) -> int:
        return 0


@dataclass
class FakeUnitOfWork:
    """Satisfies every `I…UnitOfWork` Protocol the module 7 Use Cases declare."""

    card_images: FakeCardImages = field(default_factory=FakeCardImages)
    ocr_sessions: _Store = field(default_factory=_Store)
    ocr_results: FakeOcrResults = field(default_factory=FakeOcrResults)
    customers: FakeCustomers = field(default_factory=FakeCustomers)
    bank_accounts: FakeBankAccounts = field(default_factory=FakeBankAccounts)
    templates: FakeTemplates = field(default_factory=FakeTemplates)
    template_versions: FakeTemplateVersions = field(
        default_factory=FakeTemplateVersions
    )
    contracts: _Store = field(default_factory=_Store)
    contract_documents: FakeContractDocuments = field(
        default_factory=FakeContractDocuments
    )
    jobs: FakeJobs = field(default_factory=FakeJobs)
    commits: int = 0
    entered: int = 0

    def __call__(self) -> FakeUnitOfWork:
        """The factory and the instance are the same object.

        Deliberate: a Use Case that opens two transactions must be observable
        as two `__aenter__` calls against **one** set of rows, which is exactly
        what §12.14.1 and §12.14.2 are about.
        """
        return self

    async def __aenter__(self) -> FakeUnitOfWork:
        self.entered += 1
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def ids() -> SequentialIds:
    return SequentialIds()


def make_contract_document(**overrides: Any) -> ContractDocument:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "contract_id": uuid.uuid4(),
        "file_path": "contract_document/2026/08/12/" + str(uuid.uuid4()) + ".enc",
        "file_sha256": b"\x00" * 32,
        "file_size_bytes": 1024,
        "generator": "docxtpl",
        "generation_ms": 300,
        "created_at": NOW,
    }
    defaults.update(overrides)
    return ContractDocument(**defaults)


__all__ = [
    "NOW",
    "CardImage",
    "Contract",
    "ContractDocument",
    "Customer",
    "FakeClock",
    "FakeJobRow",
    "FakeUnitOfWork",
    "OcrSession",
    "SequentialIds",
    "Template",
    "TemplateVersion",
    "make_contract_document",
]
