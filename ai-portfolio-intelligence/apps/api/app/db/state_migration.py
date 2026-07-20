"""Migrate legacy readable JSON state paths to hashed layout v2.

Compatibility constraint: record keys are recovered from the legacy filename
stem (`path.stem`). Keys that historically contained path separators or were
otherwise normalized away from a single stem cannot be reconstructed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.db.state_store import JsonStateStore, StateCorruptionError, StateStoreError

MIGRATION_MARKER = ".state-layout-v2"
_SHA256_DIR = re.compile(r"^[0-9a-f]{64}$")


def _is_hashed_component(name: str) -> bool:
    return bool(_SHA256_DIR.fullmatch(name))


def migrate_legacy_record(
    store: JsonStateStore,
    *,
    namespace: str,
    record_key: str,
    legacy_path: Path,
) -> bool:
    if not legacy_path.is_file():
        return False

    try:
        payload: Any = json.loads(legacy_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        stamp = legacy_path.with_suffix(".corrupt-pre-migration.json")
        legacy_path.replace(stamp)
        raise StateCorruptionError(
            f"Legacy state was corrupt and quarantined: {stamp.name}"
        ) from exc

    new_path = store._path(namespace, record_key)
    if not new_path.exists():
        store.write_json(namespace, record_key, payload)

    migrated = legacy_path.with_suffix(".migrated.json")
    if migrated.exists():
        migrated.unlink()
    legacy_path.rename(migrated)
    return True


def migrate_legacy_state_layout(state_root: Path) -> dict[str, Any]:
    """Rewrite pre-hash namespace/key files into the v2 hashed layout.

    Any directory under state/ whose name is not a 64-char hex digest is treated
    as a legacy namespace. Marker is written only after a full successful pass.

    The store writes into ``state_root`` explicitly so migration never depends on
    coincidentally matching process environment variables.
    """
    state_root = state_root.resolve()
    marker = state_root / MIGRATION_MARKER
    if marker.exists():
        return {
            "migrated": False,
            "already_complete": True,
            "records": 0,
        }

    store = JsonStateStore(root=state_root)
    migrated_records = 0
    skipped_hashed = 0
    errors: list[str] = []

    if not state_root.exists():
        marker.write_text("1\n", encoding="utf-8")
        return {"migrated": True, "already_complete": False, "records": 0}

    for namespace_dir in sorted(state_root.iterdir()):
        if not namespace_dir.is_dir():
            continue
        if namespace_dir.name.startswith("."):
            continue
        if _is_hashed_component(namespace_dir.name):
            skipped_hashed += 1
            continue

        namespace = namespace_dir.name
        for legacy_path in sorted(namespace_dir.glob("*.json")):
            name = legacy_path.name
            if name.endswith(".migrated.json") or ".corrupt-" in name:
                continue
            # Compatibility: only single-segment stems are recoverable.
            record_key = legacy_path.stem
            try:
                if migrate_legacy_record(
                    store,
                    namespace=namespace,
                    record_key=record_key,
                    legacy_path=legacy_path,
                ):
                    migrated_records += 1
            except (StateCorruptionError, StateStoreError, OSError) as exc:
                errors.append(f"{namespace}/{record_key}: {exc}")

    if errors:
        raise StateStoreError(
            "Legacy state migration failed; marker not written. "
            + "; ".join(errors[:5])
        )

    marker.write_text("1\n", encoding="utf-8")
    return {
        "migrated": True,
        "already_complete": False,
        "records": migrated_records,
        "skipped_hashed_namespaces": skipped_hashed,
    }
