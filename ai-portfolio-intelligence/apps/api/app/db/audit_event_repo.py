from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.legacy_bridge import read_json_with_legacy, write_json_state
from app.db.postgres_guard import require_postgres_persistence
from app.db.state_store import postgres_available

_CORE_DIR = __import__("os").path.dirname(__import__("os").path.abspath(__file__))
_APP_DIR = __import__("os").path.dirname(_CORE_DIR)
AUDIT_LOG_FILE = __import__("os").path.join(_APP_DIR, "data", "audit_logs.json")


def _table_available() -> bool:
    if not postgres_available():
        return False
    try:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(text("SELECT 1 FROM audit_events LIMIT 1"))
        return True
    except SQLAlchemyError:
        return False


def audit_events_available() -> bool:
    if settings.persistence_backend != "postgres":
        return False
    return _table_available()


def insert_audit_event(
    *,
    action: str,
    object_type: str,
    object_id: str | None,
    actor_type: str,
    actor_id: str,
    tenant_id: str | None,
    account_id: str | None,
    request_id: str | None,
    source_ip: str | None,
    outcome: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
) -> None:
    if settings.persistence_backend == "postgres":
        require_postgres_persistence("audit event write", table_available=_table_available())
    elif not _table_available():
        return

    from app.db.session import SessionLocal

    with SessionLocal() as session:
        session.execute(
            text(
                """
                INSERT INTO audit_events (
                    occurred_at,
                    actor_type,
                    actor_id,
                    tenant_id,
                    account_id,
                    action,
                    object_type,
                    object_id,
                    request_id,
                    source_ip,
                    outcome,
                    before_json,
                    after_json,
                    metadata_json
                ) VALUES (
                    :occurred_at,
                    :actor_type,
                    :actor_id,
                    :tenant_id,
                    :account_id,
                    :action,
                    :object_type,
                    :object_id,
                    :request_id,
                    :source_ip,
                    :outcome,
                    CAST(:before_json AS JSONB),
                    CAST(:after_json AS JSONB),
                    CAST(:metadata_json AS JSONB)
                )
                """
            ),
            {
                "occurred_at": datetime.now(timezone.utc),
                "actor_type": actor_type,
                "actor_id": actor_id,
                "tenant_id": tenant_id,
                "account_id": account_id,
                "action": action,
                "object_type": object_type,
                "object_id": object_id,
                "request_id": request_id,
                "source_ip": source_ip,
                "outcome": outcome,
                "before_json": json.dumps(before or {}),
                "after_json": json.dumps(after or {}),
                "metadata_json": json.dumps(metadata or {}),
            },
        )
        session.commit()


def list_audit_events(*, limit: int | None = None) -> list[dict[str, Any]] | None:
    if settings.persistence_backend == "postgres":
        require_postgres_persistence("audit event read", table_available=_table_available())
    elif not _table_available():
        return None

    from app.db.session import SessionLocal

    query = """
        SELECT
            id::text AS id,
            occurred_at,
            actor_type,
            actor_id,
            tenant_id,
            account_id,
            action,
            object_type,
            object_id,
            request_id::text AS request_id,
            host(source_ip) AS source_ip,
            outcome,
            before_json,
            after_json,
            metadata_json
        FROM audit_events
        ORDER BY occurred_at DESC
    """
    if limit is not None:
        query += " LIMIT :limit"

    with SessionLocal() as session:
        rows = session.execute(text(query), {"limit": limit} if limit is not None else {}).mappings().all()

    events: list[dict[str, Any]] = []
    for row in rows:
        payload = dict(row)
        payload["occurred_at"] = payload["occurred_at"].isoformat() if payload.get("occurred_at") else None
        events.append(payload)
    return events
