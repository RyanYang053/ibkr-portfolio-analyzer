"""Notification outbox — durable queue for desktop delivery."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.db.state_store import get_state_store

_NAMESPACE = "notification_outbox"


def enqueue_notification(
    *,
    account_id: str,
    title: str,
    body: str,
    severity: str = "info",
    category: str = "decision",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item = {
        "notification_id": f"ntf_{uuid4().hex[:12]}",
        "account_id": account_id,
        "title": title,
        "body": body,
        "severity": severity,
        "category": category,
        "payload": payload or {},
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "delivered_at": None,
    }
    store = get_state_store()
    store.write_json(_NAMESPACE, item["notification_id"], item)
    index = store.read_json(_NAMESPACE, f"index:{account_id}", default={"ids": []}) or {}
    ids = list(index.get("ids") or [])
    ids.insert(0, item["notification_id"])
    store.write_json(_NAMESPACE, f"index:{account_id}", {"ids": ids[:500]})
    pending = store.read_json(_NAMESPACE, "pending", default={"ids": []}) or {}
    pending_ids = list(pending.get("ids") or [])
    pending_ids.append(item["notification_id"])
    store.write_json(_NAMESPACE, "pending", {"ids": pending_ids})
    return item


def list_pending(limit: int = 50) -> list[dict[str, Any]]:
    store = get_state_store()
    pending = store.read_json(_NAMESPACE, "pending", default={"ids": []}) or {}
    out: list[dict[str, Any]] = []
    remaining: list[str] = []
    for notification_id in list(pending.get("ids") or []):
        row = store.read_json(_NAMESPACE, str(notification_id), default=None)
        if row and row.get("status") == "pending":
            out.append(row)
            remaining.append(str(notification_id))
            if len(out) >= limit:
                remaining.extend(list(pending.get("ids") or [])[len(remaining) :])
                break
    return out


def mark_delivered(notification_id: str) -> dict[str, Any] | None:
    store = get_state_store()
    row = store.read_json(_NAMESPACE, notification_id, default=None)
    if not row:
        return None
    row["status"] = "delivered"
    row["delivered_at"] = datetime.now(timezone.utc).isoformat()
    store.write_json(_NAMESPACE, notification_id, row)
    pending = store.read_json(_NAMESPACE, "pending", default={"ids": []}) or {}
    ids = [i for i in list(pending.get("ids") or []) if i != notification_id]
    store.write_json(_NAMESPACE, "pending", {"ids": ids})
    return row


def list_for_account(account_id: str, limit: int = 50) -> list[dict[str, Any]]:
    store = get_state_store()
    index = store.read_json(_NAMESPACE, f"index:{account_id}", default={"ids": []}) or {}
    out: list[dict[str, Any]] = []
    for notification_id in list(index.get("ids") or [])[:limit]:
        row = store.read_json(_NAMESPACE, str(notification_id), default=None)
        if row:
            out.append(row)
    return out
