"""Template endpoints — §5.2 #27 and §5.3.1 (the wizard-driving one)."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter

from cocas.application.use_cases.template.read_templates import (
    GetTemplateRequirementsUseCase,
    ListTemplatesUseCase,
)
from cocas.presentation.dependencies import ContainerDep

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("", summary="Active contract templates")
async def list_templates(container: ContainerDep) -> dict[str, Any]:
    templates = await ListTemplatesUseCase(container.unit_of_work).execute()
    return {
        "items": [
            {
                "id": str(template.id),
                "code": template.code,
                "name": template.name,
                "category": template.category,
                "has_active_version": template.has_active_version,
                "requires_images": template.requires_images,
                "sort_order": template.sort_order,
            }
            for template in templates
        ]
    }


@router.get("/{template_id}/requirements", summary="⭐ Drives the wizard (§5.3.1)")
async def template_requirements(
    template_id: uuid.UUID, container: ContainerDep
) -> dict[str, Any]:
    requirements = await GetTemplateRequirementsUseCase(container.unit_of_work).execute(
        template_id
    )
    return {
        "template_id": str(requirements.template_id),
        "code": requirements.code,
        "name": requirements.name,
        "party_schema": list(requirements.party_schema),
        "contract_fields": list(requirements.contract_fields),
        "suppressed_variables": list(requirements.suppressed_variables),
        "requires_images": requirements.requires_images,
        "active_version_no": requirements.active_version_no,
        "declared_variables": list(requirements.declared_variables),
        "required_variables": list(requirements.required_variables),
        "wizard_steps": requirements.wizard_steps,
    }
