"""Options risk snapshot persistence (plan §11 / §17)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.core.config import settings
from app.db.sql_dialect import json_cast

_NS = "option_risk_snapshots"


def _use_sql() -> bool:
    return settings.persistence_backend in {"postgres", "sqlite"}


def save_option_risk_snapshot(account_id: str, payload: dict[str, Any]) -> str:
    now = datetime.now(timezone.utc)
    snapshot_id = f"ors_{uuid4().hex[:16]}"
    if _use_sql():
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(
                text(
                    f"""
                    INSERT INTO option_risk_snapshots (snapshot_id, account_id, as_of, payload_json)
                    VALUES (:sid, :account_id, :as_of, {json_cast("payload_json")})
                    """
                ),
                {"sid": snapshot_id, "account_id": account_id, "as_of": now, "payload_json": json.dumps(payload)},
            )
            session.commit()
        return snapshot_id
    from app.db.state_store import get_state_store

    get_state_store().write_json(_NS, f"latest:{account_id}", {"snapshot_id": snapshot_id, "as_of": now.isoformat(), "payload": payload})
    return snapshot_id


def latest_option_risk_snapshot(account_id: str) -> dict[str, Any] | None:
    if _use_sql():
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            row = session.execute(
                text("SELECT payload_json FROM option_risk_snapshots WHERE account_id = :a ORDER BY as_of DESC LIMIT 1"),
                {"a": account_id},
            ).scalar()
        if row is None:
            return None
        return row if isinstance(row, dict) else json.loads(row)
    from app.db.state_store import get_state_store

    stored = get_state_store().read_json(_NS, f"latest:{account_id}", default=None)
    return stored.get("payload") if stored else None
