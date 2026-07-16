from __future__ import annotations

from datetime import date
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.postgres_guard import require_postgres_persistence, require_postgres_read
from app.db.state_store import get_state_store, postgres_available

NAMESPACE = "tax_transition_inputs"


def _table_available() -> bool:
    if not postgres_available():
        return False
    try:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(text("SELECT 1 FROM tax_transition_inputs LIMIT 1"))
        return True
    except SQLAlchemyError:
        return False


def _read_index() -> dict[str, dict[str, Any]]:
    payload = get_state_store().read_json(NAMESPACE, "index", default={})
    return payload if isinstance(payload, dict) else {}


def _write_index(index: dict[str, dict[str, Any]]) -> None:
    get_state_store().write_json(NAMESPACE, "index", index)


def upsert_tax_transition_inputs(
    *,
    account_id: str,
    jurisdiction: str,
    account_type: str,
    tax_budget: float | None,
    available_loss_offsets: float | None = None,
    wash_sale_window_days: int = 30,
    superficial_loss_window_days: int = 30,
    effective_date: date | None = None,
    source: str = "optimizer",
    constraints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    effective = effective_date or date.today()
    record = {
        "id": str(uuid4()),
        "account_id": account_id,
        "jurisdiction": jurisdiction,
        "account_type": account_type,
        "tax_budget": float(tax_budget) if tax_budget is not None else None,
        "available_loss_offsets": float(available_loss_offsets) if available_loss_offsets is not None else None,
        "wash_sale_window_days": int(wash_sale_window_days),
        "superficial_loss_window_days": int(superficial_loss_window_days),
        "effective_date": effective.isoformat(),
        "source": source,
        "constraints": constraints or {},
    }

    if settings.persistence_backend == "postgres":
        require_postgres_persistence("tax transition inputs write", table_available=_table_available())
        import json

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(
                text(
                    """
                    INSERT INTO tax_transition_inputs (
                        account_id, jurisdiction, account_type, tax_budget, available_loss_offsets,
                        wash_sale_window_days, superficial_loss_window_days, effective_date, source,
                        constraints_json
                    ) VALUES (
                        :account_id, :jurisdiction, :account_type, :tax_budget, :available_loss_offsets,
                        :wash_sale_window_days, :superficial_loss_window_days, :effective_date, :source,
                        CAST(:constraints_json AS jsonb)
                    )
                    """
                ),
                {
                    "account_id": account_id,
                    "jurisdiction": jurisdiction,
                    "account_type": account_type,
                    "tax_budget": tax_budget,
                    "available_loss_offsets": available_loss_offsets,
                    "wash_sale_window_days": wash_sale_window_days,
                    "superficial_loss_window_days": superficial_loss_window_days,
                    "effective_date": effective,
                    "source": source,
                    "constraints_json": json.dumps(constraints or {}),
                },
            )
            session.commit()
        return record

    index = _read_index()
    index[f"{account_id}:{effective.isoformat()}"] = record
    _write_index(index)
    return record


def get_latest_tax_transition_inputs(account_id: str, *, as_of: date | None = None) -> dict[str, Any] | None:
    as_of = as_of or date.today()
    if settings.persistence_backend == "postgres":
        available = _table_available()
        require_postgres_read("tax transition inputs read", table_available=available)
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            row = session.execute(
                text(
                    """
                    SELECT account_id, jurisdiction, account_type, tax_budget, available_loss_offsets,
                           wash_sale_window_days, superficial_loss_window_days, effective_date, source,
                           constraints_json
                    FROM tax_transition_inputs
                    WHERE account_id = :account_id AND effective_date <= :as_of
                    ORDER BY effective_date DESC, created_at DESC
                    LIMIT 1
                    """
                ),
                {"account_id": account_id, "as_of": as_of},
            ).mappings().first()
        if row is None:
            return None
        return {
            "account_id": row["account_id"],
            "jurisdiction": row["jurisdiction"],
            "account_type": row["account_type"],
            "tax_budget": float(row["tax_budget"]) if row["tax_budget"] is not None else None,
            "available_loss_offsets": (
                float(row["available_loss_offsets"]) if row["available_loss_offsets"] is not None else None
            ),
            "wash_sale_window_days": int(row["wash_sale_window_days"]),
            "superficial_loss_window_days": int(row["superficial_loss_window_days"]),
            "effective_date": row["effective_date"].isoformat(),
            "source": row["source"],
            "constraints": dict(row["constraints_json"] or {}),
        }

    index = _read_index()
    candidates: list[dict[str, Any]] = []
    for item in index.values():
        if not isinstance(item, dict) or item.get("account_id") != account_id:
            continue
        effective = date.fromisoformat(str(item.get("effective_date", "1900-01-01")))
        if effective <= as_of:
            candidates.append(item)
    if not candidates:
        return None
    candidates.sort(key=lambda item: str(item.get("effective_date", "")), reverse=True)
    return dict(candidates[0])
