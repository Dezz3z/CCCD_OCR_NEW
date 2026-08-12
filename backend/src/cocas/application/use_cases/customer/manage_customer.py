"""`POST /customers` (§5.3.7) and the duplicate check that precedes it (§5.2 #18).

⭐ The two belong together. §5.4 calls the search first and the create second,
and `COCAS-5002` exists because creating a second customer for one CCCD is the
mistake this flow is shaped to prevent — a person signing two contracts must
be one row, or their contract history splits in half.

⚠️ The search is **not** a substitute for the constraint. `customer.id_number_bidx`
is UNIQUE; the pre-check exists so the user sees "this person already exists,
open them" instead of a 409 after filling in a form. Two users creating the
same customer at the same instant still collide at the database, which is the
only place that can decide.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from types import TracebackType
from typing import Protocol

from loguru import logger

from cocas.domain.entities.bank_account import BankAccount
from cocas.domain.entities.customer import Customer
from cocas.domain.enums.data_quality import DataQuality
from cocas.domain.enums.gender import Gender
from cocas.domain.exceptions import DuplicateEntityError
from cocas.domain.ports.system import IClock, IIdGenerator
from cocas.domain.value_objects.bank_account_number import BankAccountNumber
from cocas.domain.value_objects.citizen_id import CitizenId
from cocas.domain.value_objects.email_address import EmailAddress
from cocas.domain.value_objects.id_card_dates import IdCardDates
from cocas.domain.value_objects.issue_place import IssuePlace
from cocas.domain.value_objects.person_name import PersonName
from cocas.domain.value_objects.securities_account_number import SecuritiesAccountNumber
from cocas.domain.value_objects.vietnamese_phone import VietnamesePhone


class ICustomerStore(Protocol):
    async def get(self, entity_id: object) -> Customer | None: ...

    async def add(self, entity: Customer) -> None: ...

    async def find_by_id_number(self, id_number: str) -> Customer | None: ...


class IBankAccountWriter(Protocol):
    async def add(self, entity: BankAccount) -> None: ...

    async def list_for_customer(self, customer_id: uuid.UUID) -> list[BankAccount]: ...


class ICustomerUnitOfWork(Protocol):
    customers: ICustomerStore
    bank_accounts: IBankAccountWriter

    async def __aenter__(self) -> ICustomerUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


@dataclass(frozen=True, slots=True)
class BankAccountRequest:
    account_number: str
    bank_name: str
    branch: str
    bank_code: str | None = None
    account_holder_name: str | None = None


@dataclass(frozen=True, slots=True)
class CreateCustomerCommand:
    full_name: str
    id_number: str
    date_of_birth: date
    issue_date: date
    expiry_date: date | None
    issue_place: str
    phone: str
    email: str
    address: str
    created_by: str
    gender: str | None = None
    province_code: str | None = None
    securities_account_no: str | None = None
    securities_account_opened_at: date | None = None
    ocr_session_id: uuid.UUID | None = None
    note: str | None = None
    bank_account: BankAccountRequest | None = None


@dataclass(frozen=True, slots=True)
class CreatedCustomer:
    customer_id: uuid.UUID
    bank_account_id: uuid.UUID | None
    full_name: str
    id_number: str


@dataclass(frozen=True, slots=True)
class CustomerWithAccounts:
    """A found customer plus what the caller needs to continue with them."""

    customer: Customer
    bank_accounts: tuple[BankAccount, ...]


class FindCustomerByIdNumberUseCase:
    """§5.2 #18 with `?id_number=…&exact=true`."""

    def __init__(self, uow_factory: Callable[[], ICustomerUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def execute(self, id_number: str) -> CustomerWithAccounts | None:
        async with self._uow_factory() as uow:
            customer = await uow.customers.find_by_id_number(id_number)
            if customer is None:
                return None
            accounts = await uow.bank_accounts.list_for_customer(customer.id)
        return CustomerWithAccounts(customer=customer, bank_accounts=tuple(accounts))


class CreateCustomerUseCase:
    """§5.3.7 `POST /customers` — the customer and, optionally, one bank account."""

    def __init__(
        self,
        uow_factory: Callable[[], ICustomerUnitOfWork],
        clock: IClock,
        id_generator: IIdGenerator,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._id_generator = id_generator

    async def execute(self, command: CreateCustomerCommand) -> CreatedCustomer:
        now = self._clock.now()
        # ⭐ Value objects are constructed here, before the transaction opens.
        # Each one validates in its constructor (§8), so an invalid CCCD or a
        # malformed phone raises without ever having started a transaction the
        # database would then have to roll back.
        customer = Customer(
            id=self._id_generator.new_id(),
            created_by=command.created_by,
            full_name=PersonName(command.full_name),
            id_number=CitizenId(command.id_number),
            date_of_birth=command.date_of_birth,
            issue_place=IssuePlace(command.issue_place),
            id_card_dates=IdCardDates(command.issue_date, command.expiry_date),
            phone=VietnamesePhone(command.phone),
            email=EmailAddress(command.email),
            address=command.address,
            data_quality=(
                DataQuality.OCR_VERIFIED
                if command.ocr_session_id is not None
                else DataQuality.MANUAL
            ),
            created_at=now,
            ocr_session_id=command.ocr_session_id,
            gender=Gender(command.gender) if command.gender else None,
            securities_account_no=(
                SecuritiesAccountNumber(command.securities_account_no)
                if command.securities_account_no
                else None
            ),
            securities_account_opened_at=command.securities_account_opened_at,
            province_code=command.province_code,
            note=command.note,
        )

        bank_account: BankAccount | None = None
        if command.bank_account is not None:
            request = command.bank_account
            bank_account = BankAccount(
                id=self._id_generator.new_id(),
                customer_id=customer.id,
                account_number=BankAccountNumber(request.account_number),
                bank_name=request.bank_name,
                branch=request.branch,
                created_at=now,
                bank_code=request.bank_code,
                account_holder_name=request.account_holder_name,
                is_primary=True,
            )

        async with self._uow_factory() as uow:
            existing = await uow.customers.find_by_id_number(command.id_number)
            if existing is not None:
                raise DuplicateEntityError(
                    "Số CCCD này đã có trong hệ thống.",
                    code="DUPLICATE_ID_NUMBER",
                    hint="Mở hồ sơ khách hàng đã có thay vì tạo mới.",
                    details={"customer_id": str(existing.id)},
                )
            await uow.customers.add(customer)
            if bank_account is not None:
                await uow.bank_accounts.add(bank_account)
            await uow.commit()

        logger.info(
            "customer created",
            customer_id=str(customer.id),
            has_bank_account=bank_account is not None,
            from_ocr=command.ocr_session_id is not None,
        )
        return CreatedCustomer(
            customer_id=customer.id,
            bank_account_id=bank_account.id if bank_account else None,
            full_name=str(customer.full_name),
            id_number=str(customer.id_number),
        )
