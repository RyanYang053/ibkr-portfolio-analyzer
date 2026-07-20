"""Desktop-only secret management for Flex tokens (OS keychain)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth_deps import get_current_principal
from app.core.config import is_desktop_local
from app.services.secrets.secret_store import get_secret_store

router = APIRouter(
    prefix="/desktop/secrets",
    tags=["desktop-secrets"],
    dependencies=[Depends(get_current_principal)],
)


class FlexTokenInput(BaseModel):
    token: str = Field(min_length=20, max_length=500)


@router.get("/flex-token")
def flex_token_status() -> dict:
    if not is_desktop_local():
        raise HTTPException(status_code=404, detail="Not available")
    configured = bool(get_secret_store().get("ibkr_flex_token"))
    return {"configured": configured}


@router.put("/flex-token")
def save_flex_token(payload: FlexTokenInput) -> dict:
    if not is_desktop_local():
        raise HTTPException(status_code=404, detail="Not available")
    get_secret_store().set("ibkr_flex_token", payload.token)
    return {"configured": True}


@router.delete("/flex-token")
def delete_flex_token() -> dict:
    if not is_desktop_local():
        raise HTTPException(status_code=404, detail="Not available")
    get_secret_store().delete("ibkr_flex_token")
    return {"configured": False}
