"""Behavioral tests for the fake ports themselves — these fakes are shared
test infrastructure for every future module, so their own invariants need
coverage now, before anything else depends on them.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cocas.domain.enums.job_status import JobStatus
from cocas.domain.enums.job_type import JobType
from cocas.domain.exceptions import DecryptionError, VaultFileNotFoundError
from cocas.domain.ports.crypto import AadContext, BidxField
from cocas.domain.ports.persistence import Specification
from cocas.domain.ports.storage import VaultCategory
from tests.fixtures.fake_ports import (
    FakeUnitOfWork,
    FrozenClock,
    InMemoryFileStorage,
    InMemoryJobQueue,
    InMemoryRepository,
    NullCryptoService,
    SequentialIdGenerator,
)

NOW = datetime(2026, 8, 9, tzinfo=UTC)


class _Entity:
    def __init__(self, id: uuid.UUID, name: str, deleted_at: datetime | None = None) -> None:
        self.id = id
        self.name = name
        self.deleted_at = deleted_at


class TestNullCryptoService:
    """⭐ Proves the cell-permutation defence (§12.17) even in the fake."""

    def test_round_trip(self) -> None:
        crypto = NullCryptoService()
        aad = AadContext(entity_id="cust-1", table_name="customer", column_name="id_number_enc")
        ciphertext = crypto.encrypt(b"001199012345", aad)
        assert crypto.decrypt(ciphertext, aad) == b"001199012345"

    def test_wrong_aad_fails_decryption(self) -> None:
        crypto = NullCryptoService()
        aad = AadContext(entity_id="cust-1", table_name="customer", column_name="id_number_enc")
        wrong_aad = AadContext(entity_id="cust-2", table_name="customer", column_name="id_number_enc")
        ciphertext = crypto.encrypt(b"001199012345", aad)
        with pytest.raises(DecryptionError):
            crypto.decrypt(ciphertext, wrong_aad)

    def test_blind_index_is_deterministic(self) -> None:
        crypto = NullCryptoService()
        first = crypto.blind_index("0912345678", BidxField.PHONE)
        second = crypto.blind_index("0912345678", BidxField.PHONE)
        assert first == second
        assert len(first) == 16

    def test_blind_index_differs_by_field(self) -> None:
        crypto = NullCryptoService()
        phone_idx = crypto.blind_index("123", BidxField.PHONE)
        email_idx = crypto.blind_index("123", BidxField.EMAIL)
        assert phone_idx != email_idx


class TestFakeUnitOfWork:
    """⭐ §12.14: leaving `async with` without commit() rolls back."""

    async def test_commit_prevents_rollback(self) -> None:
        uow = FakeUnitOfWork()
        async with uow:
            await uow.commit()
        assert uow.committed is True
        assert uow.rolled_back is False

    async def test_no_commit_triggers_rollback(self) -> None:
        uow = FakeUnitOfWork()
        async with uow:
            pass
        assert uow.rolled_back is True

    async def test_exception_still_rolls_back(self) -> None:
        uow = FakeUnitOfWork()
        with pytest.raises(ValueError):
            async with uow:
                raise ValueError("boom")
        assert uow.rolled_back is True


class TestInMemoryFileStorage:
    def test_save_then_load_round_trip(self) -> None:
        storage = InMemoryFileStorage()
        ref = storage.save(b"image-bytes", VaultCategory.CARD_IMAGE)
        assert storage.load(ref) == b"image-bytes"

    def test_ref_path_has_category_prefix(self) -> None:
        storage = InMemoryFileStorage()
        ref = storage.save(b"x", VaultCategory.THUMBNAIL)
        assert ref.relative_path.startswith("thumbnail/")

    def test_load_missing_file_raises(self) -> None:
        storage = InMemoryFileStorage()
        ref = storage.save(b"x", VaultCategory.CARD_IMAGE)
        storage.delete(ref)
        with pytest.raises(VaultFileNotFoundError):
            storage.load(ref)

    def test_exists(self) -> None:
        storage = InMemoryFileStorage()
        ref = storage.save(b"x", VaultCategory.TEMPLATE)
        assert storage.exists(ref) is True
        storage.delete(ref)
        assert storage.exists(ref) is False


class TestInMemoryRepository:
    async def test_add_then_get(self) -> None:
        repo = InMemoryRepository()
        entity_id = uuid.uuid4()
        await repo.add(_Entity(entity_id, "Nguyễn Văn An"))
        found = await repo.get(entity_id)
        assert found is not None
        assert found.name == "Nguyễn Văn An"

    async def test_list_excludes_soft_deleted_by_default(self) -> None:
        repo = InMemoryRepository(
            [_Entity(uuid.uuid4(), "a"), _Entity(uuid.uuid4(), "b", deleted_at=NOW)]
        )
        page = await repo.list(Specification())
        assert page.total == 1

    async def test_list_can_include_deleted(self) -> None:
        repo = InMemoryRepository(
            [_Entity(uuid.uuid4(), "a"), _Entity(uuid.uuid4(), "b", deleted_at=NOW)]
        )
        page = await repo.list(Specification(include_deleted=True))
        assert page.total == 2

    async def test_filters_by_attribute(self) -> None:
        repo = InMemoryRepository([_Entity(uuid.uuid4(), "a"), _Entity(uuid.uuid4(), "b")])
        page = await repo.list(Specification(filters={"name": "b"}))
        assert page.total == 1
        assert page.items[0].name == "b"

    async def test_exists(self) -> None:
        entity_id = uuid.uuid4()
        repo = InMemoryRepository([_Entity(entity_id, "a")])
        assert await repo.exists(Specification(filters={"name": "a"})) is True
        assert await repo.exists(Specification(filters={"name": "nope"})) is False

    async def test_update_records_expected_version(self) -> None:
        entity_id = uuid.uuid4()
        repo = InMemoryRepository([_Entity(entity_id, "a")])
        entity = await repo.get(entity_id)
        await repo.update(entity, expected_version=1)
        assert repo.updated == [(entity, 1)]


class TestInMemoryJobQueue:
    async def test_enqueue_returns_queued_job(self) -> None:
        queue = InMemoryJobQueue()
        job_id = await queue.enqueue(JobType.OCR)
        status = await queue.get_status(job_id)
        assert status is not None
        assert status.status == JobStatus.QUEUED

    async def test_cancel_queued_job(self) -> None:
        queue = InMemoryJobQueue()
        job_id = await queue.enqueue(JobType.TEMPLATE_VALIDATE)
        assert await queue.cancel(job_id) is True
        status = await queue.get_status(job_id)
        assert status is not None
        assert status.status == JobStatus.CANCELLED

    async def test_cancel_unknown_job_returns_false(self) -> None:
        queue = InMemoryJobQueue()
        assert await queue.cancel(uuid.uuid4()) is False

    async def test_start_stop(self) -> None:
        queue = InMemoryJobQueue()
        await queue.start()
        assert queue.started is True
        await queue.stop(graceful_timeout=1.0)
        assert queue.started is False


class TestFrozenClock:
    def test_now_and_today(self) -> None:
        clock = FrozenClock(NOW)
        assert clock.now() == NOW
        assert clock.today() == NOW.date()

    def test_advance(self) -> None:
        clock = FrozenClock(NOW)
        clock.advance(3600)
        assert clock.now().hour == NOW.hour + 1


class TestSequentialIdGenerator:
    def test_ids_are_distinct_and_ordered(self) -> None:
        gen = SequentialIdGenerator()
        first = gen.new_id()
        second = gen.new_id()
        assert first != second
        assert int(first) < int(second)
