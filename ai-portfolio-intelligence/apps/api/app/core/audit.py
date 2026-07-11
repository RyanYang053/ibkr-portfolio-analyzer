from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.core.request_context import get_request_context
from app.db.audit_event_repo import audit_events_available, insert_audit_event, list_audit_events
from app.db.legacy_bridge import read_json_with_legacy, write_json_state

_CORE_DIR = __import__("os").path.dirname(__import__("os").path.abspath(__file__))
_APP_DIR = __import__("os").path.dirname(_CORE_DIR)
AUDIT_LOG_FILE = __import__("os").path.join(_APP_DIR, "data", "audit_logs.json")


def log_audit_action(
    *,
    action: str,
    object_type: str,
    object_id: str | None = None,
    actor_id: str | None = None,
    tenant_id: str | None = None,
    account_id: str | None = None,
    outcome: str = "success",
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    actor_type: str = "user",
    critical: bool = False,
) -> None:
    context = get_request_context()
    resolved_actor = (actor_id or context.actor_id or "system").lower()
    resolved_tenant = (tenant_id or context.tenant_id or resolved_actor).lower()
    resolved_account = account_id or context.account_id
    resolved_request_id = context.request_id
    resolved_source_ip = context.source_ip
    payload_metadata = dict(metadata or {})
    if resolved_request_id and "request_id" not in payload_metadata:
        payload_metadata["request_id"] = resolved_request_id

    try:
        if audit_events_available():
            insert_audit_event(
                action=action,
                object_type=object_type,
                object_id=object_id,
                actor_type=actor_type,
                actor_id=resolved_actor,
                tenant_id=resolved_tenant,
                account_id=resolved_account,
                request_id=resolved_request_id,
                source_ip=resolved_source_ip,
                outcome=outcome,
                before=before,
                after=after,
                metadata=payload_metadata,
            )
            return

        if settings.persistence_backend == "postgres":
            raise RuntimeError("Audit event persistence requires the audit_events table in postgres mode")

        logs = read_json_with_legacy("audit_logs", "events", AUDIT_LOG_FILE, default=[])
        if not isinstance(logs, list):
            logs = []
        logs.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action": action,
                "object_type": object_type,
                "object_id": object_id,
                "actor_id": resolved_actor,
                "tenant_id": resolved_tenant,
                "account_id": resolved_account,
                "request_id": resolved_request_id,
                "source_ip": resolved_source_ip,
                "outcome": outcome,
                "before_json": json.dumps(before or {}),
                "after_json": json.dumps(after or {}),
                "metadata_json": json.dumps(payload_metadata),
            }
        )
        write_json_state("audit_logs", "events", logs)
    except Exception as exc:
        if critical:
            raise RuntimeError(f"Critical audit event persistence failed: {exc}") from exc
        raise


def get_audit_logs() -> list[dict[str, Any]]:
    if audit_events_available():
        events = list_audit_events()
        if events is not None:
            return events

    logs = read_json_with_legacy("audit_logs", "events", AUDIT_LOG_FILE, default=None)
    if isinstance(logs, list) and logs:
        return logs

    if settings.environment != "development":
        return []

    return [
        {"action": "app_started", "object_type": "system", "object_id": "local-api", "outcome": "success"},
        {
            "action": "mock_data_disabled",
            "object_type": "configuration",
            "object_id": "BROKER_MODE=mock_ibkr_readonly",
            "outcome": "success",
        },
    ]
