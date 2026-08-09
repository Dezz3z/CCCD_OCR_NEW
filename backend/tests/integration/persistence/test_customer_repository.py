"""Integration tests for SqlAlchemyCustomerRepository — REAL PostgreSQL, REAL crypto.

⭐ This is the M1 milestone test (roadmap §14.3): "script tạo Customer giả
trong CSDL, đọc lại, xác nhận id_number_enc là nhị phân không đọc được bằng
công cụ DB bên ngoài." `test_id_number_is_unreadable_binary_at_rest` below
is exactly that check, run against the real table.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import UTC, date, datetime

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from cocas.domain.entities.customer import Customer
from cocas.domain.enums.data_quality import DataQuality
from cocas.domain.ports.persistence import Specification
from cocas.domain.value_objects.citizen_id import CitizenId
from cocas.domain.value_objects.email_address import EmailAddress
from cocas.domain.value_objects.id_card_dates import IdCardDates
from cocas.domain.value_objects.issue_place import BO_CONG_AN, IssuePlace
from cocas.domain.value_objects.person_name import PersonName
from cocas.domain.value_objects.vietnamese_phone import VietnamesePhone
from cocas.infrastructure.persistence.repositories.customer_repository import (
    SqlAlchemyCustomerRepository,
)
from cocas.infrastructure.security.crypto import DpapiCryptoService

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 9, tzinfo=UTC)


@pytest.fixture
def crypto() -> DpapiCryptoService:
    return DpapiCryptoService(secrets.token_bytes(32))


@pytest_asyncio.fixture
async def repo(pg_session: AsyncSession, crypto: DpapiCryptoService) -> SqlAlchemyCustomerRepository:
    return SqlAlchemyCustomerRepository(pg_session, crypto)


def _make_customer(**overrides: object) -> Customer:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "created_by": "phthang",
        "full_name": PersonName("NGUYỄN VĂN AN"),
        "id_number": CitizenId("001199012345"),
        "date_of_birth": date(1990, 5, 14),
        "issue_place": IssuePlace(BO_CONG_AN),
        "id_card_dates": IdCardDates(date(2021, 5, 14), date(2031, 5, 14)),
        "phone": VietnamesePhone("0912345678"),
        "email": EmailAddress("an@example.com"),
        "address": "123 Đường Láng, Đống Đa, Hà Nội",
        "data_quality": DataQuality.OCR_VERIFIED,
        "created_at": NOW,
    }
    defaults.update(overrides)
    return Customer(**defaults)  # type: ignore[arg-type]


class TestAddAndGet:
    @pytest.mark.asyncio
    async def test_round_trip(self, pg_session: AsyncSession, repo: SqlAlchemyCustomerRepository) -> None:
        customer = _make_customer()
        await repo.add(customer)
        await pg_session.commit()

        loaded = await repo.get(customer.id)
        assert loaded is not None
        assert loaded.id == customer.id
        assert loaded.full_name.value == "NGUYỄN VĂN AN"
        assert loaded.id_number.value == "001199012345"
        assert loaded.date_of_birth == date(1990, 5, 14)
        assert loaded.address == "123 Đường Láng, Đống Đa, Hà Nội"
        assert loaded.phone.value == "0912345678"
        assert loaded.email.value == "an@example.com"
        assert loaded.issue_place.value == BO_CONG_AN
        assert loaded.id_card_dates.issue_date == date(2021, 5, 14)
        assert loaded.id_card_dates.expiry_date == date(2031, 5, 14)

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(
        self, repo: SqlAlchemyCustomerRepository
    ) -> None:
        assert await repo.get(uuid.uuid4()) is None

    @pytest.mark.asyncio
    async def test_id_number_is_unreadable_binary_at_rest(
        self, pg_session: AsyncSession, repo: SqlAlchemyCustomerRepository
    ) -> None:
        """⭐ M1 milestone check — read the raw column via SQL, not the repository."""
        customer = _make_customer(id_number=CitizenId("001199012345"))
        await repo.add(customer)
        await pg_session.commit()

        raw = (
            await pg_session.execute(
                text("SELECT id_number_enc, id_number_masked FROM customer WHERE id = :id"),
                {"id": customer.id},
            )
        ).one()
        id_number_enc, id_number_masked = raw

        assert isinstance(id_number_enc, bytes | memoryview)
        assert b"001199012345" not in bytes(id_number_enc)
        assert id_number_masked == "••••••••2345"


class TestBlindIndexLookup:
    @pytest.mark.asyncio
    async def test_find_by_id_number_blind_index(
        self, pg_session: AsyncSession, repo: SqlAlchemyCustomerRepository, crypto: DpapiCryptoService
    ) -> None:
        from cocas.domain.ports.crypto import BidxField

        customer = _make_customer(id_number=CitizenId("001199012345"))
        await repo.add(customer)
        await pg_session.commit()

        bidx = crypto.blind_index("001199012345", BidxField.ID_NUMBER)
        page = await repo.list(Specification(filters={"id_number_bidx": bidx}))
        assert page.total == 1
        assert page.items[0].id == customer.id

    @pytest.mark.asyncio
    async def test_duplicate_id_number_blind_index_rejected(
        self, pg_session: AsyncSession, repo: SqlAlchemyCustomerRepository
    ) -> None:
        """⭐ `uq_customer__id_number` — DuplicateEntityError, not a raw IntegrityError."""
        from cocas.domain.exceptions import DuplicateEntityError

        first = _make_customer(id_number=CitizenId("001199012345"))
        await repo.add(first)
        await pg_session.commit()

        second = _make_customer(id_number=CitizenId("001199012345"))
        with pytest.raises(DuplicateEntityError):
            await repo.add(second)
            await pg_session.commit()


class TestSoftDelete:
    @pytest.mark.asyncio
    async def test_deleted_customer_excluded_by_default(
        self, pg_session: AsyncSession, repo: SqlAlchemyCustomerRepository
    ) -> None:
        customer = _make_customer()
        await repo.add(customer)
        await pg_session.commit()

        customer.soft_delete(NOW)
        await repo.update(customer)
        await pg_session.commit()

        page = await repo.list(Specification(filters={}))
        assert customer.id not in {c.id for c in page.items}

    @pytest.mark.asyncio
    async def test_deleted_customer_included_when_requested(
        self, pg_session: AsyncSession, repo: SqlAlchemyCustomerRepository
    ) -> None:
        customer = _make_customer()
        await repo.add(customer)
        await pg_session.commit()
        customer.soft_delete(NOW)
        await repo.update(customer)
        await pg_session.commit()

        page = await repo.list(Specification(filters={}, include_deleted=True))
        assert customer.id in {c.id for c in page.items}


class TestCrossInstanceDecryption:
    @pytest.mark.asyncio
    async def test_same_kek_different_repository_instance_decrypts(
        self, pg_session: AsyncSession
    ) -> None:
        """Simulates a new process (fresh KEK-derived service, same key material)
        reading data written by a previous one — proves nothing is bound to a
        single in-memory `DpapiCryptoService` instance.
        """
        kek = secrets.token_bytes(32)
        writer = SqlAlchemyCustomerRepository(pg_session, DpapiCryptoService(kek))
        customer = _make_customer()
        await writer.add(customer)
        await pg_session.commit()

        reader = SqlAlchemyCustomerRepository(pg_session, DpapiCryptoService(kek))
        loaded = await reader.get(customer.id)
        assert loaded is not None
        assert loaded.id_number.value == "001199012345"
