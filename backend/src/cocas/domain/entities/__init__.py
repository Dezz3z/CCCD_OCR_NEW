"""Domain entities — mutable objects with identity, per docs/design/04-co-so-du-lieu.md.

Hold decrypted, plain business values — the ORM/`_enc`/`_bidx` split is a
persistence concern, translated by repositories/mappers (Infrastructure).
"""
from cocas.domain.entities.bank_account import BankAccount
from cocas.domain.entities.card_image import CardImage
from cocas.domain.entities.contract import Contract, IVersionedEntity
from cocas.domain.entities.contract_party import ContractParty
from cocas.domain.entities.customer import Customer
from cocas.domain.entities.ocr_session import OcrSession
from cocas.domain.entities.template import Template
from cocas.domain.entities.template_version import TemplateVersion

__all__ = [
    "BankAccount",
    "CardImage",
    "Contract",
    "ContractParty",
    "Customer",
    "IVersionedEntity",
    "OcrSession",
    "Template",
    "TemplateVersion",
]
