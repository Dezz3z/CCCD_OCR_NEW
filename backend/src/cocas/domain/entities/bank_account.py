"""BankAccount entity (§4.4.7 `bank_account`)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from cocas.domain.exceptions import BusinessRuleViolation
from cocas.domain.value_objects.bank_account_number import BankAccountNumber


@dataclass(slots=True)
class BankAccount:
    """A customer's bank account, used to disburse funds under a contract.

    ⭐ `bank_name` is a **copy** of the bank's display name at the time of
    entry (§4.4.7) — banks rename, but a printed contract must keep the
    name as it was when signed.
    """

    id: uuid.UUID
    customer_id: uuid.UUID
    account_number: BankAccountNumber
    bank_name: str
    branch: str
    created_at: datetime
    bank_code: str | None = None
    account_holder_name: str | None = None
    is_primary: bool = True
    updated_at: datetime | None = None
    deleted_at: datetime | None = None

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self, now: datetime) -> None:
        if self.is_deleted:
            raise BusinessRuleViolation(
                "Tài khoản ngân hàng đã bị xoá trước đó.", code="ALREADY_DELETED"
            )
        self.deleted_at = now
        self.updated_at = now
