"""Personal desktop data export and status."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth_deps import Principal, get_current_principal
from app.core.config import is_desktop_local
from app.core.desktop_bootstrap import export_desktop_archive, portfolio_data_root

router = APIRouter(prefix="/desktop", tags=["desktop"])


@router.get("/status")
def desktop_status(principal: Principal = Depends(get_current_principal)) -> dict:
    root = portfolio_data_root()
    return {
        "deployment_mode": "desktop_local" if is_desktop_local() else "development",
        "owner_id": principal.user_id,
        "data_root": str(root),
        "login_required": False if is_desktop_local() else True,
        "trading": "disabled",
    }


@router.post("/ui-ready")
def desktop_ui_ready(principal: Principal = Depends(get_current_principal)) -> dict:
    """Mark that the bundled webview successfully reached protected UI."""
    if not is_desktop_local():
        raise HTTPException(status_code=404, detail="Not available")
    root = portfolio_data_root()
    marker = root / "ui-ready.json"
    payload = {
        "ready": True,
        "owner_id": principal.user_id,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    marker.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return {"ready": True}


@router.post("/export")
def desktop_export(principal: Principal = Depends(get_current_principal)) -> dict:
    if not is_desktop_local():
        raise HTTPException(status_code=400, detail="Export endpoint is for desktop_local mode")
    path = export_desktop_archive()
    return {
        "export_path": str(path),
        "owner_id": principal.user_id,
        "includes_secrets": False,
        "note": "Flex tokens remain in the OS keychain and are not exported.",
    }
