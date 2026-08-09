"""Domain value objects — immutable, self-validating primitives.

🟢 Zero external dependency — see docs/design/11-cau-truc-va-thu-vien.md §11.5.
"""
from cocas.domain.value_objects.bank_account_number import BankAccountNumber
from cocas.domain.value_objects.citizen_id import CitizenId
from cocas.domain.value_objects.confidence_score import ConfidenceScore
from cocas.domain.value_objects.email_address import EmailAddress
from cocas.domain.value_objects.id_card_dates import IdCardDates
from cocas.domain.value_objects.issue_place import IssuePlace
from cocas.domain.value_objects.person_name import PersonName
from cocas.domain.value_objects.securities_account_number import SecuritiesAccountNumber
from cocas.domain.value_objects.styled_value import StyledValue
from cocas.domain.value_objects.vietnamese_phone import VietnamesePhone

__all__ = [
    "BankAccountNumber",
    "CitizenId",
    "ConfidenceScore",
    "EmailAddress",
    "IdCardDates",
    "IssuePlace",
    "PersonName",
    "SecuritiesAccountNumber",
    "StyledValue",
    "VietnamesePhone",
]
