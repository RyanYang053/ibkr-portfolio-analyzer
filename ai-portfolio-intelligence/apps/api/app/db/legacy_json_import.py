"""Atomic legacy JSON namespace import into desktop state / sqlite bootstrap path."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

KNOWN_NAMESPACES = (
    "decision_packets",
    "financial_plans",
    "research_candidates",
    "notification_outbox",
    "monitoring_events",
    "decision_monitoring_rules",
    "holding_theses",
    "resolved_alerts",
    "decision_outcome_history",
    "methodology_approvals",
)


def _iter_json_records(namespace_dir: Path) -> list[tuple[str, Any]]:
    records: list[tuple[str, Any]] = []
    for path in sorted(namespace_dir.rglob("*.json")):
        if path.name.startswith("."):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        # Prefer explicit key in payload; else use relative stem path.
        key = None
        if isinstance(payload, dict):
            key = payload.get("record_key") or payload.get("id") or payload.get("decision_id")
        if not key:
            key = path.stem
        records.append((str(key), payload))
    return records


def import_legacy_json_into_state_store(
    *,
    source_dir: Path,
    namespaces: tuple[str, ...] = KNOWN_NAMESPACES,
) -> dict[str, Any]:
    """Import JSON namespace folders into the active state store (sqlite/postgres/json)."""
    from app.db.state_store import get_state_store

    store = get_state_store()
    source_dir = Path(source_dir)
    imported: dict[str, int] = {}
    skipped: list[str] = []
    for namespace in namespaces:
        ns_dir = source_dir / namespace
        if not ns_dir.exists():
            # Also try hashed layout under state root (legacy JsonStateStore).
            skipped.append(namespace)
            continue
        count = 0
        for record_key, payload in _iter_json_records(ns_dir):
            store.write_json(namespace, record_key, payload)
            count += 1
        imported[namespace] = count
    return {
        "imported": imported,
        "skipped": skipped,
        "migrated_at": datetime.now(timezone.utc).isoformat(),
    }


def import_legacy_json_state(
    *,
    source_dir: Path,
    target_dir: Path,
    backup_dir: Path | None = None,
    into_state_store: bool = True,
) -> dict[str, Any]:
    """Copy known JSON namespaces atomically: backup → copy → mark migrated.

    When into_state_store is True, also write records into the active StateStore
    (SQLite/Postgres when configured).
    """
    source_dir = Path(source_dir)
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root = Path(backup_dir) if backup_dir else target_dir.parent / "backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    backup_path = backup_root / f"legacy-json-import-{stamp}"
    backup_path.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    skipped: list[str] = []

    # Backup existing target namespaces first
    for namespace in KNOWN_NAMESPACES:
        dst_ns = target_dir / namespace
        if dst_ns.exists():
            shutil.copytree(dst_ns, backup_path / namespace, dirs_exist_ok=True)

    staging = target_dir.parent / f".import-staging-{stamp}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    try:
        for namespace in KNOWN_NAMESPACES:
            src_ns = source_dir / namespace
            if not src_ns.exists():
                skipped.append(namespace)
                continue
            shutil.copytree(src_ns, staging / namespace, dirs_exist_ok=True)
            copied.append(namespace)

        for namespace in copied:
            dest = target_dir / namespace
            if dest.exists():
                shutil.rmtree(dest)
            shutil.move(str(staging / namespace), str(dest))

        store_import: dict[str, Any] | None = None
        if into_state_store:
            store_import = import_legacy_json_into_state_store(source_dir=target_dir)

        marker = {
            "migrated_at": datetime.now(timezone.utc).isoformat(),
            "copied_namespaces": copied,
            "skipped_namespaces": skipped,
            "backup_path": str(backup_path),
            "source_dir": str(source_dir),
            "target_dir": str(target_dir),
            "state_store_import": store_import,
        }
        marker_path = target_dir / "legacy_json_migrated.json"
        marker_path.write_text(json.dumps(marker, indent=2, sort_keys=True), encoding="utf-8")
        return marker
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
