"""SQLAlchemy repository implementations of `IReadRepository`/`IWriteRepository` (§12.14).

⭐ **All 9 entity repositories now exist.** `Contract` was the last one, held
back through P1 and P2 on purpose: `contract.render_snapshot_enc` is NOT NULL,
and nothing could produce that ciphertext until `RenderContextBuilder`
(§12.9) existed. P3 module 4 built it, so the repository follows — and the
snapshot arrives through `stage_snapshot()` rather than on the entity, for
the reason documented there.
"""
from cocas.infrastructure.persistence.repositories.alias_repository import (
    SqlAlchemyAliasRepository,
)
from cocas.infrastructure.persistence.repositories.bank_account_repository import (
    SqlAlchemyBankAccountRepository,
)
from cocas.infrastructure.persistence.repositories.card_image_repository import (
    SqlAlchemyCardImageRepository,
)
from cocas.infrastructure.persistence.repositories.contract_document_repository import (
    SqlAlchemyContractDocumentRepository,
)
from cocas.infrastructure.persistence.repositories.contract_party_repository import (
    SqlAlchemyContractPartyRepository,
)
from cocas.infrastructure.persistence.repositories.contract_repository import (
    SqlAlchemyContractRepository,
)
from cocas.infrastructure.persistence.repositories.customer_repository import (
    SqlAlchemyCustomerRepository,
)
from cocas.infrastructure.persistence.repositories.document_type_repository import (
    SqlAlchemyDocumentTypeRepository,
)
from cocas.infrastructure.persistence.repositories.ocr_result_repository import (
    SqlAlchemyOcrResultRepository,
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

__all__ = [
    "SqlAlchemyAliasRepository",
    "SqlAlchemyBankAccountRepository",
    "SqlAlchemyCardImageRepository",
    "SqlAlchemyContractDocumentRepository",
    "SqlAlchemyContractPartyRepository",
    "SqlAlchemyContractRepository",
    "SqlAlchemyCustomerRepository",
    "SqlAlchemyDocumentTypeRepository",
    "SqlAlchemyOcrResultRepository",
    "SqlAlchemyOcrSessionRepository",
    "SqlAlchemyTemplateRepository",
    "SqlAlchemyTemplateVersionRepository",
]
