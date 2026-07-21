"""Notification dispatcher — enqueue + deliver pending outbox items."""

from __future__ import annotations

from typing import Any

from app.services.notifications import outbox
from app.services.notifications.desktop import deliver_desktop_notification


def dispatch_decision_alert(
    *,
    account_id: str,
    title: str,
    body: str,
    severity: str = "info",
    decision_id: str | None = None,
) -> dict[str, Any]:
    item = outbox.enqueue_notification(
        account_id=account_id,
        title=title,
        body=body,
        severity=severity,
        category="decision",
        payload={"decision_id": decision_id} if decision_id else {},
    )
    if deliver_desktop_notification(item):
        delivered = outbox.mark_delivered(item["notification_id"])
        return delivered or item
    return item


def flush_pending(limit: int = 50) -> list[dict[str, Any]]:
    delivered: list[dict[str, Any]] = []
    for item in outbox.list_pending(limit=limit):
        if deliver_desktop_notification(item):
            row = outbox.mark_delivered(item["notification_id"])
            if row:
                delivered.append(row)
    return delivered
