"""Desktop local data directory, backup, and bootstrap."""

from __future__ import annotations

import hashlib
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import is_desktop_local, settings
from app.core.local_runtime import application_support_dir

MAX_BACKUPS = 10


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prune_old_backups(root: Path) -> None:
    backups = sorted(
        (root / "backups").glob("portfolio-backup-*.zip"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for stale in backups[MAX_BACKUPS:]:
        stale.unlink(missing_ok=True)


def backup_desktop_data(
    *,
    reason: str = "startup",
    passphrase: str | None = None,
) -> Path | None:
    """Zip local desktop data before schema/bootstrap changes.

    When passphrase is provided, also write an encrypted PAEB1 envelope beside the zip.
    """
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
            "persistence_backend": settings.persistence_backend,
        }
        archive.writestr("backup-meta.json", json.dumps(meta, indent=2, sort_keys=True))
    if passphrase:
        from app.services.backup.encrypted_backup import write_encrypted_backup

        encrypted = backup_path.with_suffix(".zip.paeb1")
        write_encrypted_backup(backup_path, encrypted, passphrase)
    prune_old_backups(root)
    return backup_path


def export_desktop_archive() -> Path:
    """Create a user-facing export zip under exports/."""
    root = portfolio_data_root()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    export_path = root / "exports" / f"portfolio-export-{stamp}.zip"
    files: list[dict[str, object]] = []
    manifest: dict[str, object] = {
        "schema_version": 1,
        "application_version": "0.1.0",
        "commit_sha": os.getenv("GIT_SHA", "unknown"),
        "created_at": stamp,
        "deployment_mode": "desktop_local",
        "files": files,
    }
    with zipfile.ZipFile(export_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for folder in ("state", "imports"):
            base = root / folder
            if not base.exists():
                continue
            for path in base.rglob("*"):
                if not path.is_file():
                    continue
                archive_name = str(path.relative_to(root))
                archive.write(path, arcname=archive_name)
                files.append(
                    {
                        "path": archive_name,
                        "sha256": sha256_file(path),
                        "size_bytes": path.stat().st_size,
                    }
                )
        archive.writestr(
            "export-manifest.json",
            json.dumps(manifest, indent=2, sort_keys=True),
        )
        archive.writestr(
            "EXPORT_README.txt",
            "Portfolio Analyzer personal data export.\n"
            "Secrets (Flex tokens) are stored in the OS keychain and are not included.\n",
        )
    return export_path


def bootstrap_desktop_persistence() -> dict[str, object]:
    """Prepare local personal storage. Supports JSON and SQLite desktop backends."""
    root = portfolio_data_root()
    backup = backup_desktop_data(reason="bootstrap")
    from app.db.state_migration import migrate_legacy_state_layout

    migration = migrate_legacy_state_layout(root / "state")

    sqlite_url = ""
    legacy_import: dict[str, object] | None = None
    if settings.persistence_backend == "sqlite":
        from app.core.local_runtime import default_sqlite_url
        from app.db.legacy_json_import import import_legacy_json_into_state_store
        from app.db.state_store import ensure_sql_state_table

        # Prefer configured URL; otherwise use Application Support default.
        if str(settings.database_url or "").startswith("sqlite"):
            sqlite_url = str(settings.database_url)
        else:
            sqlite_url = default_sqlite_url()
            settings.database_url = sqlite_url
        ensure_sql_state_table()
        try:
            from app.db.sqlite_desktop_schema import ensure_decision_os_sqlite_tables

            ensure_decision_os_sqlite_tables()
        except Exception as exc:  # noqa: BLE001
            legacy_import = {"schema_error": str(exc)}
        marker_path = root / "state" / "legacy_json_migrated.json"
        if not marker_path.exists() and (root / "state").exists():
            # One-time import of any plain JSON namespaces into SQLite state store.
            try:
                legacy_import = import_legacy_json_into_state_store(source_dir=root / "state")
                marker_path.write_text(
                    json.dumps(
                        {
                            "migrated_at": datetime.now(timezone.utc).isoformat(),
                            "via": "bootstrap_desktop_persistence",
                            "result": legacy_import,
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            except Exception as exc:  # noqa: BLE001 — bootstrap must not crash desktop
                legacy_import = {"error": str(exc)}

    marker = root / "desktop-bootstrap.json"
    payload: dict[str, object] = {
        "bootstrapped_at": datetime.now(timezone.utc).isoformat(),
        "persistence_backend": settings.persistence_backend,
        "backup": str(backup) if backup else "",
        "data_root": str(root),
        "state_migration": migration,
        "sqlite_url": sqlite_url,
        "legacy_json_import": legacy_import or {},
    }
    marker.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
