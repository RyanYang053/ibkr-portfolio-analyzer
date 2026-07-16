from __future__ import annotations

from datetime import date
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.postgres_guard import require_postgres_persistence, require_postgres_read
from app.db.state_store import get_state_store, postgres_available

NAMESPACE = "tax_lot_snapshots"


def _table_available() -> bool:
    if not postgres_available():
        return False
    try:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(text("SELECT 1 FROM tax_lot_snapshots LIMIT 1"))
        return True
    except SQLAlchemyError:
        return False


def _read_index() -> dict[str, list[dict[str, Any]]]:
    payload = get_state_store().read_json(NAMESPACE, "index", default={})
    return payload if isinstance(payload, dict) else {}


def _write_index(index: dict[str, list[dict[str, Any]]]) -> None:
    get_state_store().write_json(NAMESPACE, "index", index)


def _snapshot_key(account_id: str, as_of_date: date) -> str:
    return f"{account_id}:{as_of_date.isoformat()}"


def replace_tax_lot_snapshots(
    *,
    account_id: str,
    as_of_date: date,
    lots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for lot in lots:
        acquired = lot.get("acquired_date")
        if isinstance(acquired, date):
            acquired_iso = acquired.isoformat()
        else:
            acquired_iso = str(acquired)
        records.append(
            {
                "id": str(uuid4()),
                "account_id": account_id,
                "symbol": str(lot.get("symbol", "")).upper(),
                "con_id": lot.get("con_id"),
                "quantity": float(lot["quantity"]),
                "cost_basis_per_share": float(lot["cost_basis_per_share"]),
                "acquired_date": acquired_iso,
                "currency": str(lot.get("currency") or "USD"),
                "jurisdiction": str(lot.get("jurisdiction") or "OTHER"),
                "lot_method": str(lot.get("lot_method") or "fifo"),
                "as_of_date": as_of_date.isoformat(),
                "source": str(lot.get("source") or "optimizer"),
                "payload": dict(lot.get("payload") or {}),
            }
        )

    if settings.persistence_backend == "postgres":
        require_postgres_persistence("tax lot snapshot write", table_available=_table_available())
        import json

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(
                text("DELETE FROM tax_lot_snapshots WHERE account_id = :account_id AND as_of_date = :as_of_date"),
                {"account_id": account_id, "as_of_date": as_of_date},
            )
            for record in records:
                session.execute(
                    text(
                        """
                        INSERT INTO tax_lot_snapshots (
                            account_id, symbol, con_id, quantity, cost_basis_per_share, acquired_date,
                            currency, jurisdiction, lot_method, as_of_date, source, payload_json
                        ) VALUES (
                            :account_id, :symbol, :con_id, :quantity, :cost_basis_per_share, :acquired_date,
                            :currency, :jurisdiction, :lot_method, :as_of_date, :source,
                            CAST(:payload_json AS jsonb)
                        )
                        """
                    ),
                    {
                        "account_id": account_id,
                        "symbol": record["symbol"],
                        "con_id": record["con_id"],
                        "quantity": record["quantity"],
                        "cost_basis_per_share": record["cost_basis_per_share"],
                        "acquired_date": date.fromisoformat(record["acquired_date"]),
                        "currency": record["currency"],
                        "jurisdiction": record["jurisdiction"],
                        "lot_method": record["lot_method"],
                        "as_of_date": as_of_date,
                        "source": record["source"],
                        "payload_json": json.dumps(record["payload"]),
                    },
                )
            session.commit()
        return records

    index = _read_index()
    index[_snapshot_key(account_id, as_of_date)] = records
    _write_index(index)
    return records


def list_tax_lot_snapshots(
    account_id: str,
    *,
    as_of_date: date | None = None,
) -> list[dict[str, Any]]:
    as_of_date = as_of_date or date.today()
    if settings.persistence_backend == "postgres":
        available = _table_available()
        require_postgres_read("tax lot snapshot read", table_available=available)
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            rows = session.execute(
                text(
                    """
                    SELECT account_id, symbol, con_id, quantity, cost_basis_per_share, acquired_date,
                           currency, jurisdiction, lot_method, as_of_date, source, payload_json
                    FROM tax_lot_snapshots
                    WHERE account_id = :account_id AND as_of_date = :as_of_date
                    ORDER BY symbol ASC, acquired_date ASC
                    """
                ),
                {"account_id": account_id, "as_of_date": as_of_date},
            ).mappings().all()
        return [
            {
                "account_id": row["account_id"],
                "symbol": row["symbol"],
                "con_id": row["con_id"],
                "quantity": float(row["quantity"]),
                "cost_basis_per_share": float(row["cost_basis_per_share"]),
                "acquired_date": row["acquired_date"].isoformat(),
                "currency": row["currency"],
                "jurisdiction": row["jurisdiction"],
                "lot_method": row["lot_method"],
                "as_of_date": row["as_of_date"].isoformat(),
                "source": row["source"],
                "payload": dict(row["payload_json"] or {}),
            }
            for row in rows
        ]

    index = _read_index()
    records = index.get(_snapshot_key(account_id, as_of_date), [])
    return [dict(item) for item in records if isinstance(item, dict)]
