"""Customer endpoints — §5.3.7 `POST /customers` and the exact-match lookup."""
from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response, status
from pydantic import BaseModel, Field

from cocas.application.use_cases.customer.manage_customer import (
    BankAccountRequest,
    CreateCustomerCommand,
    CustomerWithAccounts,
)
from cocas.presentation.dependencies import ContainerDep

router = APIRouter(prefix="/customers", tags=["customers"])


class BankAccountBody(BaseModel):
    account_number: Annotated[str, Field(min_length=6, max_length=30)]
    bank_name: Annotated[str, Field(min_length=1, max_length=150)]
    branch: Annotated[str, Field(min_length=1, max_length=150)]
    bank_code: str | None = None
    account_holder_name: str | None = None


class CreateCustomerBody(BaseModel):
    full_name: Annotated[str, Field(min_length=2, max_length=100)]
    id_number: Annotated[str, Field(min_length=12, max_length=12)]
    date_of_birth: date
    issue_date: date
    #: `None` means "KHÔNG THỜI HẠN" — a real value, not a missing one
    #: (`IdCardDates`). Absent and null therefore mean the same thing here.
    expiry_date: date | None = None
    issue_place: str
    phone: str
    email: str
    address: Annotated[str, Field(min_length=10, max_length=300)]
    created_by: str = "desktop"
    gender: str | None = None
    province_code: str | None = None
    securities_account_no: str | None = None
    securities_account_opened_at: date | None = None
    ocr_session_id: uuid.UUID | None = None
    note: str | None = None
    bank_account: BankAccountBody | None = None


def _summary(found: CustomerWithAccounts) -> dict[str, Any]:
    customer = found.customer
    return {
        "id": str(customer.id),
        "full_name": str(customer.full_name),
        "id_number": str(customer.id_number),
        "date_of_birth": customer.date_of_birth.isoformat(),
        "issue_place": str(customer.issue_place),
        "phone": str(customer.phone),
        "email": str(customer.email),
        "data_quality": customer.data_quality.value,
        "created_at": customer.created_at.isoformat(),
        # ⭐ Carried on the duplicate check, not left for a second round trip:
        # the caller looked this person up in order to keep going, and for the
        # GDN template keeping going needs a `bank_account_id` (`COCAS-7012`).
        "bank_accounts": [
            {
                "id": str(account.id),
                "account_number": str(account.account_number),
                "bank_name": account.bank_name,
                "bank_code": account.bank_code,
                "branch": account.branch,
                "is_primary": account.is_primary,
            }
            for account in found.bank_accounts
        ],
    }


@router.get("", summary="§5.4 step 11 — duplicate check by CCCD")
async def search_customers(
    container: ContainerDep,
    id_number: Annotated[str | None, Query(min_length=12, max_length=12)] = None,
    exact: bool = False,
) -> dict[str, Any]:
    """Only the exact-CCCD form is implemented for the demo slice.

    ⚠️ Says so rather than silently returning an empty page: a search endpoint
    that answers `{"items": []}` to a query it does not support reads as "no
    such customer", which is the one wrong answer this call must never give.
    """
    if id_number is None or not exact:
        return {
            "items": [],
            "unsupported_query": True,
            "hint": "Bản demo chỉ hỗ trợ ?id_number=<12 số>&exact=true.",
        }
    found = await container.find_customer_use_case().execute(id_number)
    return {"items": [_summary(found)] if found else []}


@router.post("", status_code=status.HTTP_201_CREATED, summary="§5.3.7 create")
async def create_customer(
    body: CreateCustomerBody, container: ContainerDep, response: Response
) -> dict[str, Any]:
    created = await container.create_customer_use_case().execute(
        CreateCustomerCommand(
            full_name=body.full_name,
            id_number=body.id_number,
            date_of_birth=body.date_of_birth,
            issue_date=body.issue_date,
            expiry_date=body.expiry_date,
            issue_place=body.issue_place,
            phone=body.phone,
            email=body.email,
            address=body.address,
            created_by=body.created_by,
            gender=body.gender,
            province_code=body.province_code,
            securities_account_no=body.securities_account_no,
            securities_account_opened_at=body.securities_account_opened_at,
            ocr_session_id=body.ocr_session_id,
            note=body.note,
            bank_account=(
                BankAccountRequest(
                    account_number=body.bank_account.account_number,
                    bank_name=body.bank_account.bank_name,
                    branch=body.bank_account.branch,
                    bank_code=body.bank_account.bank_code,
                    account_holder_name=body.bank_account.account_holder_name,
                )
                if body.bank_account
                else None
            ),
        )
    )
    response.headers["Location"] = f"/api/v1/customers/{created.customer_id}"
    return {
        "id": str(created.customer_id),
        "full_name": created.full_name,
        "id_number": created.id_number,
        "bank_account_id": (
            str(created.bank_account_id) if created.bank_account_id else None
        ),
    }
