from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.postgres_guard import require_postgres_persistence
from app.db.state_store import get_state_store, postgres_available
from app.schemas.domain import Position


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _table_available() -> bool:
    if not postgres_available():
        return False
    try:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(text("SELECT 1 FROM daily_position_snapshots LIMIT 1"))
        return True
    except SQLAlchemyError:
        return False


def upsert_daily_positions(account_id: str, snapshot_date: date, positions: list[Position]) -> None:
    rows: list[dict[str, Any]] = []
    for position in positions:
        if position.quantity == 0:
            continue
        rows.append(
            {
                "symbol": position.symbol.upper(),
                "con_id": position.con_id,
                "quantity": float(position.quantity),
                "market_value": float(position.market_value),
                "currency": position.currency,
                "sector": position.sector,
                "asset_class": position.asset_class,
            }
        )

    if settings.persistence_backend == "postgres":
        require_postgres_persistence("daily position snapshot write", table_available=_table_available())
        from app.db.session import SessionLocal

        now = _utc_now()
        with SessionLocal() as session:
            for row in rows:
                payload = json.dumps(row)
                session.execute(
                    text(
                        """
                        INSERT INTO daily_position_snapshots (
                            account_id, snapshot_date, symbol, con_id, quantity, market_value,
                            currency, payload_json, created_at
                        ) VALUES (
                            :account_id, :snapshot_date, :symbol, :con_id, :quantity, :market_value,
                            :currency, :payload_json, :created_at
                        )
                        ON CONFLICT ON CONSTRAINT uq_daily_position_snapshots_account_date_symbol
                        DO UPDATE SET
                            quantity = EXCLUDED.quantity,
                            market_value = EXCLUDED.market_value,
                            currency = EXCLUDED.currency,
                            payload_json = EXCLUDED.payload_json,
                            created_at = EXCLUDED.created_at
                        """
                    ),
                    {
                        "account_id": account_id,
                        "snapshot_date": snapshot_date,
                        "symbol": row["symbol"],
                        "con_id": row["con_id"],
                        "quantity": row["quantity"],
                        "market_value": row["market_value"],
                        "currency": row["currency"],
                        "payload_json": payload,
                        "created_at": now,
                    },
                )
            session.commit()
        return

    store = get_state_store()
    store.write_json(
        "daily_position_snapshots",
        f"{account_id}:{snapshot_date.isoformat()}",
        rows,
    )


def read_daily_positions(account_id: str, snapshot_date: date) -> list[dict[str, Any]]:
    if settings.persistence_backend == "postgres" and _table_available():
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            result = session.execute(
                text(
                    """
                    SELECT payload_json
                    FROM daily_position_snapshots
                    WHERE account_id = :account_id AND snapshot_date = :snapshot_date
                    ORDER BY symbol ASC
                    """
                ),
                {"account_id": account_id, "snapshot_date": snapshot_date},
            ).fetchall()
        rows: list[dict[str, Any]] = []
        for item in result:
            try:
                rows.append(json.loads(item.payload_json))
            except json.JSONDecodeError:
                continue
        return rows

    payload = get_state_store().read_json(
        "daily_position_snapshots",
        f"{account_id}:{snapshot_date.isoformat()}",
        default=[],
    )
    return payload if isinstance(payload, list) else []
