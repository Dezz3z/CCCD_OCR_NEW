"""SQLAlchemy repository implementations of `IReadRepository`/`IWriteRepository` (§12.14).

⚠️ `Contract` has no repository yet — `contract.render_snapshot_enc` is
`NOT NULL` in the schema, but the `Contract` domain entity (built in the
Entities module) never carries that ciphertext, only its hash
(`snapshot_sha256`). Producing the actual encrypted snapshot is
`RenderContextBuilder` + `DocxRenderer`'s job (§12.9–12.11), which doesn't
exist until P3. Building a Contract repository now would guess at a shape
that P3 will very likely change — deferred on purpose (P-10).
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
from cocas.infrastructure.persistence.repositories.contract_party_repository import (
    SqlAlchemyContractPartyRepository,
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
    "SqlAlchemyContractPartyRepository",
    "SqlAlchemyCustomerRepository",
    "SqlAlchemyDocumentTypeRepository",
    "SqlAlchemyOcrResultRepository",
    "SqlAlchemyOcrSessionRepository",
    "SqlAlchemyTemplateRepository",
    "SqlAlchemyTemplateVersionRepository",
]
