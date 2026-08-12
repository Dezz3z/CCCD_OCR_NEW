"""Contract endpoints — §5.3.8 generate and §5.3.9 download."""
from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from cocas.application.dto.contract import GenerateContractCommand, PartyRequest
from cocas.domain.enums.entity_type import EntityType
from cocas.presentation.dependencies import ContainerDep

router = APIRouter(prefix="/contracts", tags=["contracts"])

DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


class PartyBody(BaseModel):
    party_key: str = "holder"
    customer_id: uuid.UUID
    party_index: int = 0
    entity_type: EntityType = EntityType.INDIVIDUAL
    bank_account_id: uuid.UUID | None = None
    ocr_session_id: uuid.UUID | None = None
    is_primary: bool = True
    party_extra: dict[str, Any] = Field(default_factory=dict)


class GenerateContractBody(BaseModel):
    template_id: uuid.UUID
    parties: Annotated[list[PartyBody], Field(min_length=1, max_length=10)]
    created_by: str = "desktop"
    created_by_name: str = ""
    contract_date: date | None = None
    extra_variables: dict[str, Any] = Field(default_factory=dict)


@router.post("/generate", status_code=status.HTTP_201_CREATED, summary="§5.3.8")
async def generate_contract(
    body: GenerateContractBody, container: ContainerDep, response: Response
) -> dict[str, Any]:
    result = await container.generate_contract_use_case().execute(
        GenerateContractCommand(
            template_id=body.template_id,
            parties=[
                PartyRequest(
                    party_key=party.party_key,
                    customer_id=party.customer_id,
                    party_index=party.party_index,
                    entity_type=party.entity_type,
                    bank_account_id=party.bank_account_id,
                    ocr_session_id=party.ocr_session_id,
                    is_primary=party.is_primary,
                    party_extra=dict(party.party_extra),
                )
                for party in body.parties
            ],
            created_by=body.created_by,
            created_by_name=body.created_by_name,
            contract_date=body.contract_date,
            extra_variables=dict(body.extra_variables),
        )
    )
    response.headers["Location"] = f"/api/v1/contracts/{result.contract_id}"
    return {
        "id": str(result.contract_id),
        "contract_no": result.contract_no,
        "export_name": result.export_name,
        "status": "COMPLETED",
        "document_id": str(result.document_id),
        "file_sha256": result.file_sha256.hex(),
        "file_size_bytes": result.file_size_bytes,
        "generation_ms": result.generation_ms,
        "created_at": result.created_at.isoformat(),
        "download_url": f"/api/v1/contracts/{result.contract_id}/documents/docx",
        # ⭐ 🟡 findings travel with the success body, not as an error: the
        # contract exists and is valid, and hiding "the card has expired"
        # because nothing blocked would waste the one moment the user can act.
        "warnings": [
            {"code": finding.code, "message": finding.message}
            for finding in result.warnings.warnings
        ],
    }


@router.get("/{contract_id}/documents/docx", summary="§5.3.9 stream the .docx")
async def download_docx(contract_id: uuid.UUID, container: ContainerDep) -> Response:
    document = await container.download_contract_document_use_case().execute(
        contract_id
    )
    # ⚠️ RFC 5987 `filename*`, because export names are Vietnamese
    # (`Mẫu 01A - NGUYỄN VĂN AN.docx`) and a raw non-ASCII `filename=` is not
    # transmissible in a header. The ASCII `filename=` stays as the fallback
    # for anything that does not understand the extended form.
    encoded = quote(document.file_name)
    return Response(
        content=document.content,
        media_type=DOCX_MEDIA_TYPE,
        headers={
            "Content-Disposition": (
                f'attachment; filename="contract.docx"; filename*=UTF-8\'\'{encoded}'
            ),
            "Content-Length": str(document.size_bytes),
            "X-Content-SHA256": document.sha256.hex(),
            # §5.5 #4 — the body is a contract full of PII.
            "Cache-Control": "no-store",
        },
    )
