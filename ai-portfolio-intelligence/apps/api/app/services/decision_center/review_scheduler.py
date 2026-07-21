"""Schedule and track thesis / decision review due dates."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.db.state_store import get_state_store

_NAMESPACE = "decision_review_schedule"


def upsert_review_schedule(
    *,
    account_id: str,
    instrument_key: str,
    decision_id: str,
    review_due_at: str | None = None,
    reason: str = "decision_packet",
) -> dict[str, Any]:
    due = review_due_at
    if not due:
        due = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    row = {
        "account_id": account_id,
        "instrument_key": instrument_key,
        "decision_id": decision_id,
        "review_due_at": due,
        "reason": reason,
        "status": "scheduled",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    store = get_state_store()
    key = f"{account_id}:{instrument_key}"
    store.write_json(_NAMESPACE, key, row)
    index = store.read_json(_NAMESPACE, f"index:{account_id}", default={"keys": []}) or {}
    keys = list(index.get("keys") or [])
    if key not in keys:
        keys.insert(0, key)
    store.write_json(_NAMESPACE, f"index:{account_id}", {"keys": keys[:500]})
    return row


def list_due_reviews(account_id: str, *, as_of: datetime | None = None) -> list[dict[str, Any]]:
    now = as_of or datetime.now(timezone.utc)
    store = get_state_store()
    index = store.read_json(_NAMESPACE, f"index:{account_id}", default={"keys": []}) or {}
    due: list[dict[str, Any]] = []
    for key in list(index.get("keys") or []):
        row = store.read_json(_NAMESPACE, str(key), default=None)
        if not isinstance(row, dict):
            continue
        try:
            due_at = datetime.fromisoformat(str(row.get("review_due_at")).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        if due_at <= now and row.get("status") == "scheduled":
            due.append(row)
    return due
