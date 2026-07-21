"""Application settings API (plan §17 application_settings, §24 privacy/config)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth_deps import Principal, get_current_principal
from app.db.app_settings_repo import all_settings, get_setting, set_setting

router = APIRouter(prefix="/app-settings", tags=["settings"], dependencies=[Depends(get_current_principal)])


def _owner(principal: Principal) -> str:
    return str(getattr(principal, "user_id", None) or "local-owner")


class SettingValue(BaseModel):
    value: Any


@router.get("")
def list_settings(principal: Principal = Depends(get_current_principal)) -> dict[str, Any]:
    return {"settings": all_settings(_owner(principal))}


@router.get("/{key}")
def read_setting(key: str, principal: Principal = Depends(get_current_principal)) -> dict[str, Any]:
    return {"key": key, "value": get_setting(_owner(principal), key, default=None)}


@router.put("/{key}")
def write_setting(
    key: str,
    body: SettingValue,
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    set_setting(_owner(principal), key, body.value)
    return {"key": key, "value": body.value, "persisted": True}
