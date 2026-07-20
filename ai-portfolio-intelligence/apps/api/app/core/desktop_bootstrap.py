"""Desktop local data directory, backup, and bootstrap."""

from __future__ import annotations

import json
import os
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import is_desktop_local, settings
from app.core.local_runtime import application_support_dir


def portfolio_data_root() -> Path:
    override = os.getenv("PORTFOLIO_DATA_DIR")
    if override:
        root = Path(override)
    elif is_desktop_local():
        root = application_support_dir()
    else:
        # Development fallback next to the api package.
        root = Path(__file__).resolve().parents[2] / "data"
    for sub in ("state", "imports", "exports", "backups", "logs"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def state_data_dir() -> Path:
    return portfolio_data_root() / "state"


def backup_desktop_data(*, reason: str = "startup") -> Path | None:
    """Zip local desktop data before schema/bootstrap changes."""
    if not is_desktop_local():
        return None

    root = portfolio_data_root()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = root / "backups" / f"portfolio-backup-{reason}-{stamp}.zip"
    with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        state_dir = root / "state"
        if state_dir.exists():
            for path in state_dir.rglob("*"):
                if path.is_file():
                    archive.write(path, arcname=str(path.relative_to(root)))
        db_path = root / "portfolio.db"
        if db_path.exists():
            archive.write(db_path, arcname="portfolio.db")
        meta = {
            "reason": reason,
            "created_at": stamp,
            "deployment_mode": str(settings.deployment_mode),
            "app_version": "0.1.0",
        }
        archive.writestr("backup-meta.json", json.dumps(meta, indent=2))
    return backup_path


def export_desktop_archive() -> Path:
    """Create a user-facing export zip under exports/."""
    root = portfolio_data_root()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    export_path = root / "exports" / f"portfolio-export-{stamp}.zip"
    with zipfile.ZipFile(export_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for folder in ("state", "imports"):
            base = root / folder
            if not base.exists():
                continue
            for path in base.rglob("*"):
                if path.is_file():
                    archive.write(path, arcname=str(path.relative_to(root)))
        db_path = root / "portfolio.db"
        if db_path.exists():
            archive.write(db_path, arcname="portfolio.db")
        archive.writestr(
            "EXPORT_README.txt",
            "Portfolio Analyzer personal data export.\n"
            "Secrets (Flex tokens) are stored in the OS keychain and are not included.\n",
        )
    return export_path


def bootstrap_desktop_persistence() -> dict[str, str]:
    """Prepare local personal storage. JSON state is the supported desktop path today."""
    root = portfolio_data_root()
    backup = backup_desktop_data(reason="bootstrap")
    marker = root / "desktop-bootstrap.json"
    payload = {
        "bootstrapped_at": datetime.now(timezone.utc).isoformat(),
        "persistence_backend": settings.persistence_backend,
        "backup": str(backup) if backup else "",
        "data_root": str(root),
    }
    marker.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
