from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.postgres_guard import require_postgres_persistence
from app.db.state_store import postgres_available


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _table_available() -> bool:
    if not postgres_available():
        return False
    try:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(text("SELECT 1 FROM pnl_snapshots LIMIT 1"))
        return True
    except SQLAlchemyError:
        return False


def read_pnl_snapshots(account_id: str) -> list[dict[str, Any]]:
    if settings.persistence_backend == "postgres":
        require_postgres_persistence("pnl snapshot read", table_available=_table_available())
    elif not _table_available():
        return []

    from app.db.session import SessionLocal

    with SessionLocal() as session:
        rows = session.execute(
            text(
                """
                SELECT payload_json
                FROM pnl_snapshots
                WHERE account_id = :account_id
                ORDER BY snapshot_date ASC, created_at ASC
                """
            ),
            {"account_id": account_id},
        ).fetchall()
    history: list[dict[str, Any]] = []
    for row in rows:
        try:
            history.append(json.loads(row.payload_json))
        except json.JSONDecodeError:
            continue
    return history


def upsert_pnl_snapshot(account_id: str, snapshot_date: date, snapshot: dict[str, Any]) -> None:
    if settings.persistence_backend == "postgres":
        require_postgres_persistence("pnl snapshot write", table_available=_table_available())
    elif not _table_available():
        return

    from app.db.session import SessionLocal

    now = _utc_now()
    payload_text = json.dumps(snapshot)
    with SessionLocal() as session:
        session.execute(
            text(
                """
                INSERT INTO pnl_snapshots (
                    account_id, snapshot_date, net_liquidation, cash, payload_json, created_at
                ) VALUES (
                    :account_id, :snapshot_date, :net_liquidation, :cash, :payload_json, :created_at
                )
                ON CONFLICT ON CONSTRAINT uq_pnl_snapshots_account_date
                DO UPDATE SET
                    net_liquidation = EXCLUDED.net_liquidation,
                    cash = EXCLUDED.cash,
                    payload_json = EXCLUDED.payload_json,
                    created_at = EXCLUDED.created_at
                """
            ),
            {
                "account_id": account_id,
                "snapshot_date": snapshot_date,
                "net_liquidation": float(snapshot.get("net_liquidation", 0.0)),
                "cash": float(snapshot.get("cash", 0.0)),
                "payload_json": payload_text,
                "created_at": now,
            },
        )
        session.commit()
