"""Persist computed analytics snapshots (plan §17: risk_snapshots, stress_test_runs)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.core.config import settings
from app.db.sql_dialect import json_cast


def _use_sql() -> bool:
    return settings.persistence_backend in {"postgres", "sqlite"}


def save_risk_snapshot(account_id: str, payload: dict[str, Any]) -> str | None:
    """Best-effort persistence of a computed risk snapshot. Never blocks the response."""
    now = datetime.now(timezone.utc)
    snapshot_id = f"risk_{uuid4().hex[:16]}"
    try:
        if _use_sql():
            from sqlalchemy import text

            from app.db.session import SessionLocal

            with SessionLocal() as session:
                session.execute(
                    text(
                        f"""
                        INSERT INTO risk_snapshots (snapshot_id, account_id, as_of, payload_json, created_at)
                        VALUES (:sid, :account_id, :as_of, {json_cast("payload_json")}, :created_at)
                        """
                    ),
                    {"sid": snapshot_id, "account_id": account_id, "as_of": now,
                     "payload_json": json.dumps(payload), "created_at": now},
                )
                session.commit()
        else:
            from app.db.state_store import get_state_store

            get_state_store().write_json("risk_snapshots", f"latest:{account_id}", {"as_of": now.isoformat(), "payload": payload})
    except Exception:  # noqa: BLE001 — analytics persistence must not break the read path
        return None
    return snapshot_id
