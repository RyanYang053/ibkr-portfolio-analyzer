from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.postgres_guard import require_postgres_persistence
from app.db.state_store import get_state_store, postgres_available


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _table_available() -> bool:
    if not postgres_available():
        return False
    try:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(text("SELECT 1 FROM calculation_runs LIMIT 1"))
        return True
    except SQLAlchemyError:
        return False


def insert_calculation_run(run_id: str, run_type: str, account_id: str, payload: dict[str, Any]) -> None:
    methodology_version = str(payload.get("methodology_version", "unknown"))
    if settings.persistence_backend == "postgres":
        require_postgres_persistence("calculation run write", table_available=_table_available())
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(
                text(
                    """
                    INSERT INTO calculation_runs (
                        id, run_type, account_id, methodology_version, payload_json, created_at
                    ) VALUES (
                        :id, :run_type, :account_id, :methodology_version, :payload_json, :created_at
                    )
                    """
                ),
                {
                    "id": run_id,
                    "run_type": run_type,
                    "account_id": account_id,
                    "methodology_version": methodology_version,
                    "payload_json": json.dumps(payload),
                    "created_at": _utc_now(),
                },
            )
            session.commit()
        return

    store = get_state_store()
    store.write_json("calculation_runs", f"{account_id}:{run_id}", payload)


def read_calculation_run(account_id: str, run_id: str) -> dict[str, Any] | None:
    if settings.persistence_backend == "postgres":
        if not _table_available():
            return None
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            row = session.execute(
                text(
                    """
                    SELECT payload_json
                    FROM calculation_runs
                    WHERE id = :run_id AND account_id = :account_id
                    """
                ),
                {"run_id": run_id, "account_id": account_id},
            ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row.payload_json)
        except json.JSONDecodeError:
            return None

    store = get_state_store()
    payload = store.read_json("calculation_runs", f"{account_id}:{run_id}")
    return payload if isinstance(payload, dict) else None
