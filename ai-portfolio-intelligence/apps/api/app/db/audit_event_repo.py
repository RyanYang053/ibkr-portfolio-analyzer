from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
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


def _redact_value(key: str, value: Any) -> Any:
    normalized = key.lower().replace("-", "_")
    if normalized in settings.audit_sensitive_keys:
        return "[REDACTED]"
    if isinstance(value, dict):
        return _redact_mapping(value)
    if isinstance(value, list):
        return [_redact_value(str(index), item) for index, item in enumerate(value)]
    return value


def _redact_mapping(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {}
    return {key: _redact_value(key, value) for key, value in payload.items()}


def _canonical_event_json(
    *,
    occurred_at: datetime,
    actor_type: str,
    actor_id: str,
    tenant_id: str | None,
    account_id: str | None,
    action: str,
    object_type: str,
    object_id: str | None,
    request_id: str | None,
    source_ip: str | None,
    outcome: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
) -> str:
    payload = {
        "occurred_at": occurred_at.astimezone(timezone.utc).isoformat(),
        "actor_type": actor_type,
        "actor_id": actor_id,
        "tenant_id": tenant_id,
        "account_id": account_id,
        "action": action,
        "object_type": object_type,
        "object_id": object_id,
        "request_id": str(request_id) if request_id else None,
        "source_ip": source_ip,
        "outcome": outcome,
        "before": before or {},
        "after": after or {},
        "metadata": metadata or {},
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _compute_event_hash(previous_hash: str, canonical_json: str) -> str:
    digest = hashlib.sha256(f"{previous_hash}{canonical_json}".encode("utf-8")).hexdigest()
    return digest


def _latest_event_hash(session) -> str:
    row = session.execute(
        text(
            """
            SELECT event_hash
            FROM audit_events
            ORDER BY occurred_at DESC, id DESC
            LIMIT 1
            FOR UPDATE
            """
        )
    ).mappings().first()
    if not row:
        return ""
    return str(row.get("event_hash") or "")


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

    redacted_before = _redact_mapping(before)
    redacted_after = _redact_mapping(after)
    redacted_metadata = _redact_mapping(metadata)
    occurred_at = datetime.now(timezone.utc)

    from app.db.session import SessionLocal

    with SessionLocal() as session:
        previous_event_hash = _latest_event_hash(session)
        canonical_json = _canonical_event_json(
            occurred_at=occurred_at,
            actor_type=actor_type,
            actor_id=actor_id,
            tenant_id=tenant_id,
            account_id=account_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            request_id=request_id,
            source_ip=source_ip,
            outcome=outcome,
            before=redacted_before,
            after=redacted_after,
            metadata=redacted_metadata,
        )
        event_hash = _compute_event_hash(previous_event_hash, canonical_json)
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
                    metadata_json,
                    previous_event_hash,
                    event_hash
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
                    CAST(:metadata_json AS JSONB),
                    :previous_event_hash,
                    :event_hash
                )
                """
            ),
            {
                "occurred_at": occurred_at,
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
                "before_json": json.dumps(redacted_before),
                "after_json": json.dumps(redacted_after),
                "metadata_json": json.dumps(redacted_metadata),
                "previous_event_hash": previous_event_hash or None,
                "event_hash": event_hash,
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
            metadata_json,
            previous_event_hash,
            event_hash
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


def verify_audit_chain() -> dict[str, Any]:
    if not audit_events_available():
        return {"valid": False, "reason": "audit_events_unavailable"}

    from app.db.session import SessionLocal

    with SessionLocal() as session:
        rows = session.execute(
            text(
                """
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
                    metadata_json,
                    previous_event_hash,
                    event_hash
                FROM audit_events
                ORDER BY occurred_at ASC, id ASC
                """
            )
        ).mappings().all()

    previous_hash = ""
    for row in rows:
        event = dict(row)
        canonical_json = _canonical_event_json(
            occurred_at=event["occurred_at"],
            actor_type=event["actor_type"],
            actor_id=event["actor_id"],
            tenant_id=event.get("tenant_id"),
            account_id=event.get("account_id"),
            action=event["action"],
            object_type=event["object_type"],
            object_id=event.get("object_id"),
            request_id=event.get("request_id"),
            source_ip=event.get("source_ip"),
            outcome=event["outcome"],
            before=event.get("before_json"),
            after=event.get("after_json"),
            metadata=event.get("metadata_json"),
        )
        expected_hash = _compute_event_hash(previous_hash, canonical_json)
        if event.get("previous_event_hash") != (previous_hash or None):
            return {
                "valid": False,
                "broken_at": event.get("id"),
                "reason": "previous_event_hash_mismatch",
            }
        if event.get("event_hash") != expected_hash:
            return {
                "valid": False,
                "broken_at": event.get("id"),
                "reason": "event_hash_mismatch",
            }
        previous_hash = expected_hash

    return {"valid": True, "count": len(rows)}
