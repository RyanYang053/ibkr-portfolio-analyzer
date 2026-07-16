from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.postgres_guard import require_postgres_persistence, require_postgres_read
from app.db.state_store import get_state_store, postgres_available

NAMESPACE = "decision_monitoring_rules"


def _table_available() -> bool:
    if not postgres_available():
        return False
    try:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(text("SELECT 1 FROM decision_monitoring_rules LIMIT 1"))
        return True
    except SQLAlchemyError:
        return False


def _read_index() -> dict[str, dict[str, Any]]:
    payload = get_state_store().read_json(NAMESPACE, "index", default={})
    return payload if isinstance(payload, dict) else {}


def _write_index(index: dict[str, dict[str, Any]]) -> None:
    get_state_store().write_json(NAMESPACE, "index", index)


def list_rules(account_id: str) -> list[dict[str, Any]]:
    if settings.persistence_backend == "postgres" and _table_available():
        require_postgres_read("decision monitoring rules read", table_available=True)
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            rows = session.execute(
                text(
                    """
                    SELECT rule_id, account_id, instrument_key, rule_type, threshold, active,
                           payload_json, created_at
                    FROM decision_monitoring_rules
                    WHERE account_id = :account_id
                    ORDER BY created_at ASC
                    """
                ),
                {"account_id": account_id},
            ).mappings().all()
        out: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row["payload_json"] or {})
            out.append(
                {
                    "rule_id": row["rule_id"],
                    "account_id": row["account_id"],
                    "instrument_key": row["instrument_key"],
                    "rule_type": row["rule_type"],
                    "threshold": float(row["threshold"]) if row["threshold"] is not None else None,
                    "note": payload.get("note"),
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    "methodology_status": payload.get("methodology_status", "experimental"),
                    "active": bool(row["active"]),
                }
            )
        return out

    index = _read_index()
    return [
        dict(item)
        for item in index.values()
        if isinstance(item, dict) and item.get("account_id") == account_id
    ]


def create_rule(
    account_id: str,
    *,
    instrument_key: str | None,
    rule_type: str,
    threshold: float | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    rule = {
        "rule_id": str(uuid4()),
        "account_id": account_id,
        "instrument_key": instrument_key,
        "rule_type": rule_type,
        "threshold": threshold,
        "note": note,
        "created_at": now.isoformat(),
        "methodology_status": "experimental",
        "active": True,
    }
    payload = {"note": note, "methodology_status": "experimental"}

    if settings.persistence_backend == "postgres":
        require_postgres_persistence("decision monitoring rule write", table_available=_table_available())
        from app.db.session import SessionLocal
        import json

        with SessionLocal() as session:
            session.execute(
                text(
                    """
                    INSERT INTO decision_monitoring_rules (
                        rule_id, account_id, instrument_key, rule_type, threshold, active,
                        payload_json, created_at
                    ) VALUES (
                        :rule_id, :account_id, :instrument_key, :rule_type, :threshold, :active,
                        CAST(:payload_json AS jsonb), :created_at
                    )
                    """
                ),
                {
                    "rule_id": rule["rule_id"],
                    "account_id": account_id,
                    "instrument_key": instrument_key,
                    "rule_type": rule_type,
                    "threshold": threshold,
                    "active": True,
                    "payload_json": json.dumps(payload),
                    "created_at": now,
                },
            )
            session.commit()
        return rule

    index = _read_index()
    index[rule["rule_id"]] = rule
    _write_index(index)
    return rule
