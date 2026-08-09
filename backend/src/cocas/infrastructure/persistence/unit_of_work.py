"""`SqlAlchemyUnitOfWork` — implements `IUnitOfWork` (§12.14).

⭐ One Use Case = one UoW = one transaction. Leaving the `async with` block
without calling `commit()` rolls back — including on exception, and also on
a plain early `return` if the caller forgot to commit.
"""
from __future__ import annotations

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cocas.domain.ports.crypto import ICryptoService
from cocas.infrastructure.persistence.repositories.bank_account_repository import (
    SqlAlchemyBankAccountRepository,
)
from cocas.infrastructure.persistence.repositories.card_image_repository import (
    SqlAlchemyCardImageRepository,
)
from cocas.infrastructure.persistence.repositories.contract_party_repository import (
    SqlAlchemyContractPartyRepository,
)
from cocas.infrastructure.persistence.repositories.customer_repository import (
    SqlAlchemyCustomerRepository,
)
from cocas.infrastructure.persistence.repositories.ocr_session_repository import (
    SqlAlchemyOcrSessionRepository,
)
from cocas.infrastructure.persistence.repositories.template_repository import (
    SqlAlchemyTemplateRepository,
)
from cocas.infrastructure.persistence.repositories.template_version_repository import (
    SqlAlchemyTemplateVersionRepository,
)


class SqlAlchemyUnitOfWork:
    """One `AsyncSession`-scoped transaction, exposing one repository per entity.

    ⭐ File operations (Vault writes) must stay OUTSIDE this transaction —
    write-temp, `commit()`, then rename. This class only ever touches the
    database.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession], crypto: ICryptoService) -> None:
        self._session_factory = session_factory
        self._crypto = crypto
        self._session: AsyncSession | None = None
        self._committed = False

    async def __aenter__(self) -> SqlAlchemyUnitOfWork:
        self._session = self._session_factory()
        self._committed = False
        self.card_images = SqlAlchemyCardImageRepository(self._session)
        self.ocr_sessions = SqlAlchemyOcrSessionRepository(self._session)
        self.templates = SqlAlchemyTemplateRepository(self._session)
        self.template_versions = SqlAlchemyTemplateVersionRepository(self._session)
        self.contract_parties = SqlAlchemyContractPartyRepository(self._session)
        self.customers = SqlAlchemyCustomerRepository(self._session, self._crypto)
        self.bank_accounts = SqlAlchemyBankAccountRepository(self._session, self._crypto)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        assert self._session is not None
        try:
            if not self._committed:
                await self._session.rollback()
        finally:
            await self._session.close()
            self._session = None

    async def commit(self) -> None:
        assert self._session is not None
        await self._session.commit()
        self._committed = True

    async def rollback(self) -> None:
        assert self._session is not None
        await self._session.rollback()
