"""`SqlAlchemyBankAccountRepository`."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cocas.domain.entities.bank_account import BankAccount
from cocas.domain.ports.crypto import AadContext, BidxField, ICryptoService
from cocas.domain.value_objects.bank_account_number import BankAccountNumber
from cocas.infrastructure.persistence.mappers.masking import mask_keep_suffix
from cocas.infrastructure.persistence.models.bank_account import BankAccountModel
from cocas.infrastructure.persistence.repositories._base import SqlAlchemyRepository

_TABLE = "bank_account"


class SqlAlchemyBankAccountRepository(SqlAlchemyRepository[BankAccount, BankAccountModel]):
    model = BankAccountModel

    def __init__(self, session: AsyncSession, crypto: ICryptoService) -> None:
        super().__init__(session)
        self._crypto = crypto

    def _aad(self, entity_id: object, column: str) -> AadContext:
        return AadContext(entity_id=str(entity_id), table_name=_TABLE, column_name=column)

    async def list_for_customer(self, customer_id: uuid.UUID) -> list[BankAccount]:
        """A customer's live accounts, primary first.

        ⭐ Needed by the duplicate check, not just by the detail screen. §5.4
        looks a customer up by CCCD *in order to continue with them* — and for
        the GDN template continuing means naming a `bank_account_id`
        (`V-CTR-007` / `COCAS-7012`). A response that says "this person exists"
        without saying what they have leaves the caller unable to act on it.
        """
        statement = (
            select(self.model)
            .where(
                self.model.customer_id == customer_id,
                self.model.deleted_at.is_(None),
            )
            .order_by(self.model.is_primary.desc(), self.model.created_at)
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return [self._to_domain(row) for row in rows]

    def _to_domain(self, row: BankAccountModel) -> BankAccount:
        account_number_plain = self._crypto.decrypt(
            row.account_number_enc, self._aad(row.id, "account_number_enc")
        ).decode("utf-8")
        return BankAccount(
            id=row.id,
            customer_id=row.customer_id,
            account_number=BankAccountNumber(account_number_plain),
            bank_name=row.bank_name,
            branch=row.branch,
            created_at=row.created_at,
            bank_code=row.bank_code,
            account_holder_name=row.account_holder_name,
            is_primary=row.is_primary,
            updated_at=row.updated_at,
            deleted_at=row.deleted_at,
        )

    def _apply_to_row(self, entity: BankAccount, row: BankAccountModel) -> None:
        row.id = entity.id
        row.customer_id = entity.customer_id
        row.account_number_enc = self._crypto.encrypt(
            entity.account_number.value.encode("utf-8"),
            self._aad(entity.id, "account_number_enc"),
        )
        row.account_number_bidx = self._crypto.blind_index(
            entity.account_number.value, BidxField.BANK_ACCOUNT_NUMBER
        )
        row.account_number_masked = mask_keep_suffix(entity.account_number.value)
        row.bank_code = entity.bank_code
        row.bank_name = entity.bank_name
        row.branch = entity.branch
        row.account_holder_name = entity.account_holder_name
        row.is_primary = entity.is_primary
        row.created_at = entity.created_at
        row.updated_at = entity.updated_at
        row.deleted_at = entity.deleted_at
