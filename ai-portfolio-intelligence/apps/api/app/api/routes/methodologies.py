"""Methodology catalog and approval API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.auth_deps import get_current_principal
from app.services.validation.methodology_validation import (
    list_methodologies,
    record_approval,
    validate_methodology_claim,
)

router = APIRouter(
    prefix="/methodologies",
    tags=["methodologies"],
    dependencies=[Depends(get_current_principal)],
)


class ApprovalRequest(BaseModel):
    methodology_id: str
    version: str
    approver: str = "owner"
    notes: str | None = None


class ClaimValidationRequest(BaseModel):
    methodology_id: str
    claimed_status: str = Field(default="experimental")


@router.get("")
def methodologies() -> dict[str, Any]:
    return {
        "methodologies": list_methodologies(),
        "order_generated": False,
    }


@router.post("/approvals")
def approve_methodology(body: ApprovalRequest) -> dict[str, Any]:
    return record_approval(
        methodology_id=body.methodology_id,
        version=body.version,
        approver=body.approver,
        notes=body.notes,
    )


@router.post("/validate-claim")
def validate_claim(body: ClaimValidationRequest) -> dict[str, Any]:
    return validate_methodology_claim(body.methodology_id, body.claimed_status)
