"""Personal desktop data export and status."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth_deps import Principal, get_current_principal
from app.core.config import is_desktop_local, settings
from app.core.desktop_bootstrap import export_desktop_archive, portfolio_data_root

router = APIRouter(prefix="/desktop", tags=["desktop"])


@router.get("/status")
def desktop_status(principal: Principal = Depends(get_current_principal)) -> dict:
    root = portfolio_data_root()
    return {
        "deployment_mode": "desktop_local" if is_desktop_local() else "development",
        "owner_id": principal.user_id,
        "data_root": str(root),
        "persistence_backend": settings.persistence_backend,
        "login_required": False if is_desktop_local() else True,
        "trading": "disabled",
        "order_generated": False,
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


@router.get("/audit-logs")
def desktop_audit_logs(principal: Principal = Depends(get_current_principal)) -> list:
    """Local activity log for desktop (admin audit router is cloud-only)."""
    if not is_desktop_local():
        raise HTTPException(status_code=404, detail="Not available")
    from app.core.audit import get_audit_logs

    return get_audit_logs()


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


@router.post("/backup")
def desktop_backup(
    body: dict | None = None,
    principal: Principal = Depends(get_current_principal),
) -> dict:
    """Create a local backup zip; optionally encrypt with passphrase (PAEB1)."""
    if not is_desktop_local():
        raise HTTPException(status_code=400, detail="Backup endpoint is for desktop_local mode")
    from app.core.desktop_bootstrap import backup_desktop_data

    payload = body or {}
    passphrase = payload.get("passphrase")
    path = backup_desktop_data(reason=str(payload.get("reason") or "manual"), passphrase=passphrase)
    encrypted = None
    if path and passphrase:
        candidate = path.with_suffix(".zip.paeb1")
        if candidate.exists():
            encrypted = str(candidate)
    return {
        "backup_path": str(path) if path else None,
        "encrypted_path": encrypted,
        "persistence_backend": settings.persistence_backend if is_desktop_local() else None,
        "owner_id": principal.user_id,
        "order_generated": False,
        "includes_secrets": False,
    }


@router.post("/backup/verify-restore")
def desktop_verify_restore(
    body: dict | None = None,
    principal: Principal = Depends(get_current_principal),
) -> dict:
    """Verify an encrypted backup can be decrypted (does not overwrite live data)."""
    if not is_desktop_local():
        raise HTTPException(status_code=400, detail="Restore verify is for desktop_local mode")
    from pathlib import Path

    from app.services.backup.encrypted_backup import decrypt_backup_bytes

    payload = body or {}
    path = payload.get("encrypted_path")
    passphrase = payload.get("passphrase")
    if not path or not passphrase:
        raise HTTPException(status_code=400, detail="encrypted_path and passphrase are required")
    blob = Path(str(path)).read_bytes()
    plaintext = decrypt_backup_bytes(blob, str(passphrase))
    return {
        "ok": True,
        "bytes": len(plaintext),
        "owner_id": principal.user_id,
        "note": "Decryption succeeded. Live restore is a separate explicit user action.",
        "order_generated": False,
    }
