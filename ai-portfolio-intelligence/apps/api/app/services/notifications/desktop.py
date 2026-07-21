"""Desktop notification delivery (local-only)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("notifications.desktop")


def _desktop_inbox_path() -> Path:
    from app.core.desktop_bootstrap import portfolio_data_root

    path = portfolio_data_root() / "notifications"
    path.mkdir(parents=True, exist_ok=True)
    return path / "desktop_inbox.jsonl"


def deliver_desktop_notification(item: dict[str, Any]) -> bool:
    """Best-effort local delivery into a desktop-pollable inbox file."""
    try:
        record = {
            **item,
            "delivered_at": datetime.now(timezone.utc).isoformat(),
            "channel": "desktop_inbox",
        }
        inbox = _desktop_inbox_path()
        with inbox.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str) + "\n")
        logger.info(
            "desktop_notification id=%s title=%s severity=%s",
            item.get("notification_id"),
            item.get("title"),
            item.get("severity"),
        )
        return True
    except Exception as exc:
        logger.warning("desktop notification failed: %s", exc)
        return False


def read_desktop_inbox(limit: int = 50) -> list[dict[str, Any]]:
    inbox = _desktop_inbox_path()
    if not inbox.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in inbox.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(rows))
