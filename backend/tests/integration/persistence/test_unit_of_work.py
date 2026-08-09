"""Integration tests for SqlAlchemyUnitOfWork — REAL PostgreSQL.

⭐ The one invariant that matters most here (§12.14): leaving the
`async with` block without calling `commit()` rolls back everything.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from cocas.domain.entities.customer import Customer
from cocas.domain.enums.data_quality import DataQuality
from cocas.domain.value_objects.citizen_id import CitizenId
from cocas.domain.value_objects.email_address import EmailAddress
from cocas.domain.value_objects.id_card_dates import IdCardDates
from cocas.domain.value_objects.issue_place import BO_CONG_AN, IssuePlace
from cocas.domain.value_objects.person_name import PersonName
from cocas.domain.value_objects.vietnamese_phone import VietnamesePhone
from cocas.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from cocas.infrastructure.security.crypto import DpapiCryptoService

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 9, tzinfo=UTC)


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


@pytest.fixture
def crypto() -> DpapiCryptoService:
    return DpapiCryptoService(secrets.token_bytes(32))


class TestCommit:
    @pytest.mark.asyncio
    async def test_committed_data_is_visible_in_a_new_uow(
        self, pg_session_factory: async_sessionmaker, crypto: DpapiCryptoService
    ) -> None:
        customer_id = uuid.uuid4()
        async with SqlAlchemyUnitOfWork(pg_session_factory, crypto) as uow:
            await uow.customers.add(_make_customer(id=customer_id))
            await uow.commit()

        async with SqlAlchemyUnitOfWork(pg_session_factory, crypto) as uow:
            loaded = await uow.customers.get(customer_id)
        assert loaded is not None
        assert loaded.id == customer_id


class TestAutoRollback:
    @pytest.mark.asyncio
    async def test_leaving_block_without_commit_rolls_back(
        self, pg_session_factory: async_sessionmaker, crypto: DpapiCryptoService
    ) -> None:
        """⭐ §12.14: no explicit `commit()` -> nothing persisted, no error raised."""
        customer_id = uuid.uuid4()
        async with SqlAlchemyUnitOfWork(pg_session_factory, crypto) as uow:
            await uow.customers.add(_make_customer(id=customer_id))
            # deliberately no commit()

        async with SqlAlchemyUnitOfWork(pg_session_factory, crypto) as uow:
            loaded = await uow.customers.get(customer_id)
        assert loaded is None

    @pytest.mark.asyncio
    async def test_exception_inside_block_rolls_back(
        self, pg_session_factory: async_sessionmaker, crypto: DpapiCryptoService
    ) -> None:
        customer_id = uuid.uuid4()
        with pytest.raises(RuntimeError):
            async with SqlAlchemyUnitOfWork(pg_session_factory, crypto) as uow:
                await uow.customers.add(_make_customer(id=customer_id))
                raise RuntimeError("simulated use-case failure")

        async with SqlAlchemyUnitOfWork(pg_session_factory, crypto) as uow:
            loaded = await uow.customers.get(customer_id)
        assert loaded is None


class TestCrossRepositoryTransaction:
    @pytest.mark.asyncio
    async def test_customer_and_bank_account_commit_together(
        self, pg_session_factory: async_sessionmaker, crypto: DpapiCryptoService
    ) -> None:
        from cocas.domain.entities.bank_account import BankAccount
        from cocas.domain.value_objects.bank_account_number import BankAccountNumber

        customer_id = uuid.uuid4()
        async with SqlAlchemyUnitOfWork(pg_session_factory, crypto) as uow:
            await uow.customers.add(_make_customer(id=customer_id))
            await uow.bank_accounts.add(
                BankAccount(
                    id=uuid.uuid4(),
                    customer_id=customer_id,
                    account_number=BankAccountNumber("0123456789013"),
                    bank_name="Vietcombank",
                    branch="Chi nhánh Hà Nội",
                    created_at=NOW,
                )
            )
            await uow.commit()

        async with SqlAlchemyUnitOfWork(pg_session_factory, crypto) as uow:
            customer = await uow.customers.get(customer_id)
        assert customer is not None
