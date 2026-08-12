"""`SqlAlchemyCustomerRepository` — the repository that actually encrypts PII.

⭐ M1 demo target (roadmap §14.3): create a fake Customer, read it back, and
confirm `id_number_enc` is unreadable binary via an external DB tool. This
repository is where that invariant is implemented.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cocas.domain.entities.customer import Customer
from cocas.domain.enums.data_quality import DataQuality
from cocas.domain.enums.gender import Gender
from cocas.domain.ports.crypto import AadContext, BidxField, ICryptoService
from cocas.domain.value_objects._vn_text import nfc_upper, strip_diacritics
from cocas.domain.value_objects.citizen_id import CitizenId
from cocas.domain.value_objects.email_address import EmailAddress
from cocas.domain.value_objects.id_card_dates import IdCardDates
from cocas.domain.value_objects.issue_place import IssuePlace
from cocas.domain.value_objects.person_name import PersonName
from cocas.domain.value_objects.securities_account_number import SecuritiesAccountNumber
from cocas.domain.value_objects.vietnamese_phone import VietnamesePhone
from cocas.infrastructure.persistence.mappers.masking import mask_keep_suffix
from cocas.infrastructure.persistence.models.customer import CustomerModel
from cocas.infrastructure.persistence.repositories._base import SqlAlchemyRepository

_TABLE = "customer"


class SqlAlchemyCustomerRepository(SqlAlchemyRepository[Customer, CustomerModel]):
    model = CustomerModel

    def __init__(self, session: AsyncSession, crypto: ICryptoService) -> None:
        super().__init__(session)
        self._crypto = crypto

    def _aad(self, entity_id: object, column: str) -> AadContext:
        return AadContext(entity_id=str(entity_id), table_name=_TABLE, column_name=column)

    async def find_by_id_number(self, id_number: str) -> Customer | None:
        """Exact lookup on the encrypted CCCD, via its blind index (§5.3.7).

        ⭐ The blind index is the **only** way this query can exist. `id_number_enc`
        is AES-GCM with a per-row nonce, so two rows holding the same CCCD have
        different ciphertexts and `WHERE id_number_enc = :x` matches nothing —
        ever. `HMAC(PEPPER, "id_number" ‖ normalize(value))` is deterministic,
        so it can be indexed and compared.

        ⚠️ The field name is part of the HMAC input. Without it a phone number
        and a bank account number that happen to be the same digit string
        produce the same token, and a lookup crosses columns.
        """
        blind_index = self._crypto.blind_index(id_number, BidxField.ID_NUMBER)
        statement = select(self.model).where(
            self.model.id_number_bidx == blind_index,
            self.model.deleted_at.is_(None),
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return self._to_domain(row) if row is not None else None

    def _to_domain(self, row: CustomerModel) -> Customer:
        id_number_plain = self._crypto.decrypt(
            row.id_number_enc, self._aad(row.id, "id_number_enc")
        ).decode("utf-8")
        dob_plain = self._crypto.decrypt(
            row.date_of_birth_enc, self._aad(row.id, "date_of_birth_enc")
        ).decode("utf-8")
        address_plain = self._crypto.decrypt(
            row.address_enc, self._aad(row.id, "address_enc")
        ).decode("utf-8")

        return Customer(
            id=row.id,
            created_by=row.created_by,
            full_name=PersonName(row.full_name),
            id_number=CitizenId(id_number_plain),
            date_of_birth=date.fromisoformat(dob_plain),
            issue_place=IssuePlace(row.issue_place),
            id_card_dates=IdCardDates(row.issue_date, row.expiry_date),
            phone=VietnamesePhone(row.phone),
            email=EmailAddress(row.email),
            address=address_plain,
            data_quality=DataQuality(row.data_quality),
            created_at=row.created_at,
            ocr_session_id=row.ocr_session_id,
            gender=Gender(row.gender) if row.gender else None,
            securities_account_no=(
                SecuritiesAccountNumber(row.securities_account_no)
                if row.securities_account_no
                else None
            ),
            securities_account_opened_at=row.securities_account_opened_at,
            province_code=row.province_code,
            note=row.note,
            updated_at=row.updated_at,
            deleted_at=row.deleted_at,
        )

    def _apply_to_row(self, entity: Customer, row: CustomerModel) -> None:
        row.id = entity.id
        row.created_by = entity.created_by
        row.ocr_session_id = entity.ocr_session_id
        row.full_name = entity.full_name.value
        row.full_name_search = strip_diacritics(nfc_upper(entity.full_name.value))

        row.id_number_enc = self._crypto.encrypt(
            entity.id_number.value.encode("utf-8"), self._aad(entity.id, "id_number_enc")
        )
        row.id_number_bidx = self._crypto.blind_index(entity.id_number.value, BidxField.ID_NUMBER)
        row.id_number_masked = mask_keep_suffix(entity.id_number.value)

        row.date_of_birth_enc = self._crypto.encrypt(
            entity.date_of_birth.isoformat().encode("utf-8"),
            self._aad(entity.id, "date_of_birth_enc"),
        )
        row.birth_year = entity.birth_year
        row.gender = entity.gender.value if entity.gender else None
        row.issue_place = entity.issue_place.value
        row.issue_date = entity.id_card_dates.issue_date
        row.expiry_date = entity.id_card_dates.expiry_date
        row.no_expiry = entity.id_card_dates.is_no_expiry

        row.phone = entity.phone.value
        row.phone_bidx = self._crypto.blind_index(entity.phone.value, BidxField.PHONE)
        row.email = entity.email.value
        row.email_bidx = self._crypto.blind_index(entity.email.value, BidxField.EMAIL)

        row.address_enc = self._crypto.encrypt(
            entity.address.encode("utf-8"), self._aad(entity.id, "address_enc")
        )

        row.securities_account_no = (
            entity.securities_account_no.value if entity.securities_account_no else None
        )
        row.securities_account_bidx = (
            self._crypto.blind_index(
                entity.securities_account_no.value, BidxField.SECURITIES_ACCOUNT
            )
            if entity.securities_account_no
            else None
        )
        row.securities_account_opened_at = entity.securities_account_opened_at
        row.province_code = entity.province_code
        row.data_quality = entity.data_quality.value
        row.note = entity.note
        row.created_at = entity.created_at
        row.updated_at = entity.updated_at
        row.deleted_at = entity.deleted_at
