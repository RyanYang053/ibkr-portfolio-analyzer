from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

_CORE_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_DIR = os.path.dirname(_CORE_DIR)
AUDIT_LOG_FILE = os.path.join(_APP_DIR, "data", "audit_logs.json")

def log_audit_action(action: str, object_type: str, object_id: str | None = None, metadata: dict[str, Any] | None = None) -> None:
    """Record an action to the audit logs JSON file."""
    try:
        os.makedirs(os.path.dirname(AUDIT_LOG_FILE), exist_ok=True)
        logs = []
        if os.path.exists(AUDIT_LOG_FILE):
            try:
                with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
                    logs = json.load(f)
            except Exception:
                logs = []
        new_log = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "object_type": object_type,
            "object_id": object_id,
            "metadata_json": json.dumps(metadata or {})
        }
        logs.append(new_log)
        # Keep last 100 logs
        logs = logs[-100:]
        with open(AUDIT_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2)
    except Exception:
        pass

def get_audit_logs() -> list[dict[str, Any]]:
    """Retrieve all audit logs from the JSON file, or seed default records."""
    try:
        if os.path.exists(AUDIT_LOG_FILE):
            with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
    except Exception:
        pass
    
    # Return seed logs when no activity has occurred yet
    return [
        {"action": "app_started", "object_type": "system", "object_id": "local-api"},
        {"action": "mock_data_disabled", "object_type": "configuration", "object_id": "BROKER_MODE=mock_ibkr_readonly"},
    ]
