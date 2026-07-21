"""Persist alert resolution state."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.db.state_store import get_state_store

_NAMESPACE = "resolved_alerts"


def resolve_alert(alert_id: int, *, account_id: str | None = None) -> dict[str, Any]:
    store = get_state_store()
    payload = {
        "id": alert_id,
        "alert_id": alert_id,
        "account_id": account_id,
        "is_resolved": True,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    }
    store.write_json(_NAMESPACE, str(alert_id), payload)
    index = store.read_json(_NAMESPACE, "index", default={"ids": []}) or {}
    ids = list(index.get("ids") or [])
    if alert_id not in ids:
        ids.append(alert_id)
    store.write_json(_NAMESPACE, "index", {"ids": ids})
    return payload


def is_resolved(alert_id: int) -> bool:
    row = get_state_store().read_json(_NAMESPACE, str(alert_id), default=None)
    return bool(row and row.get("is_resolved"))


def list_resolved() -> list[dict[str, Any]]:
    store = get_state_store()
    index = store.read_json(_NAMESPACE, "index", default={"ids": []}) or {}
    out: list[dict[str, Any]] = []
    for alert_id in list(index.get("ids") or []):
        row = store.read_json(_NAMESPACE, str(alert_id), default=None)
        if row:
            out.append(row)
    return out
