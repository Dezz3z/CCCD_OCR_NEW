"""SQLAlchemy 2.0 ORM models — the 19 tables of docs/design/04-co-so-du-lieu.md.

✅ Verified against real PostgreSQL 18.4 — see `base.py`'s docstring.

Every model name ends in `Model` to keep it visually distinct from the
same-named Domain entity (e.g. `CustomerModel` vs `Customer`) — the
repositories in `infrastructure/persistence/repositories/` translate
between them.
"""
from cocas.infrastructure.persistence.models.activity_log import ActivityLogModel
from cocas.infrastructure.persistence.models.backup_record import BackupRecordModel
from cocas.infrastructure.persistence.models.bank_account import BankAccountModel
from cocas.infrastructure.persistence.models.bank_directory import BankDirectoryModel
from cocas.infrastructure.persistence.models.base import Base
from cocas.infrastructure.persistence.models.card_image import CardImageModel
from cocas.infrastructure.persistence.models.contract import ContractModel
from cocas.infrastructure.persistence.models.contract_document import ContractDocumentModel
from cocas.infrastructure.persistence.models.contract_party import ContractPartyModel
from cocas.infrastructure.persistence.models.contract_template import ContractTemplateModel
from cocas.infrastructure.persistence.models.customer import CustomerModel
from cocas.infrastructure.persistence.models.document_type import DocumentTypeModel
from cocas.infrastructure.persistence.models.job import JobModel
from cocas.infrastructure.persistence.models.normalization_alias import NormalizationAliasModel
from cocas.infrastructure.persistence.models.ocr_field import OcrFieldModel
from cocas.infrastructure.persistence.models.ocr_result import OcrResultModel
from cocas.infrastructure.persistence.models.ocr_session import OcrSessionModel
from cocas.infrastructure.persistence.models.province_code import ProvinceCodeModel
from cocas.infrastructure.persistence.models.system_setting import SystemSettingModel
from cocas.infrastructure.persistence.models.template_version import TemplateVersionModel

__all__ = [
    "ActivityLogModel",
    "BackupRecordModel",
    "BankAccountModel",
    "BankDirectoryModel",
    "Base",
    "CardImageModel",
    "ContractDocumentModel",
    "ContractModel",
    "ContractPartyModel",
    "ContractTemplateModel",
    "CustomerModel",
    "DocumentTypeModel",
    "JobModel",
    "NormalizationAliasModel",
    "OcrFieldModel",
    "OcrResultModel",
    "OcrSessionModel",
    "ProvinceCodeModel",
    "SystemSettingModel",
    "TemplateVersionModel",
]
