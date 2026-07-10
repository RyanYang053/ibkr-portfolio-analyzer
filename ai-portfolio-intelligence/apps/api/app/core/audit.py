from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.db.legacy_bridge import read_json_with_legacy, write_json_state

_CORE_DIR = __import__("os").path.dirname(__import__("os").path.abspath(__file__))
_APP_DIR = __import__("os").path.dirname(_CORE_DIR)
AUDIT_LOG_FILE = __import__("os").path.join(_APP_DIR, "data", "audit_logs.json")


def log_audit_action(action: str, object_type: str, object_id: str | None = None, metadata: dict[str, Any] | None = None) -> None:
    logs = read_json_with_legacy("audit_logs", "events", AUDIT_LOG_FILE, default=[])
    if not isinstance(logs, list):
        logs = []
    logs.append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "object_type": object_type,
            "object_id": object_id,
            "metadata_json": json.dumps(metadata or {}),
        }
    )
    write_json_state("audit_logs", "events", logs[-100:])


def get_audit_logs() -> list[dict[str, Any]]:
    logs = read_json_with_legacy("audit_logs", "events", AUDIT_LOG_FILE, default=None)
    if isinstance(logs, list) and logs:
        return logs
    return [
        {"action": "app_started", "object_type": "system", "object_id": "local-api"},
        {"action": "mock_data_disabled", "object_type": "configuration", "object_id": "BROKER_MODE=mock_ibkr_readonly"},
    ]
