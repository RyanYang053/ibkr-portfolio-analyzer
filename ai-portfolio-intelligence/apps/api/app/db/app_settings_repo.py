"""Application settings persistence (plan §17 application_settings)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.db.sql_dialect import json_cast

_NS = "application_settings"


def _use_sql() -> bool:
    return settings.persistence_backend in {"postgres", "sqlite"}


def set_setting(owner_id: str, key: str, value: Any) -> None:
    now = datetime.now(timezone.utc)
    if _use_sql():
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(
                text(
                    f"""
                    INSERT INTO application_settings (owner_id, key, value_json, updated_at)
                    VALUES (:owner_id, :key, {json_cast("value_json")}, :updated_at)
                    ON CONFLICT(owner_id, key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at
                    """
                ),
                {"owner_id": owner_id, "key": key, "value_json": json.dumps(value), "updated_at": now},
            )
            session.commit()
        return
    from app.db.state_store import get_state_store

    get_state_store().write_json(_NS, f"{owner_id}:{key}", {"value": value})


def get_setting(owner_id: str, key: str, default: Any = None) -> Any:
    if _use_sql():
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            row = session.execute(
                text("SELECT value_json FROM application_settings WHERE owner_id = :o AND key = :k"),
                {"o": owner_id, "k": key},
            ).scalar()
        if row is None:
            return default
        return row if not isinstance(row, str) else json.loads(row)
    from app.db.state_store import get_state_store

    stored = get_state_store().read_json(_NS, f"{owner_id}:{key}", default=None)
    return stored["value"] if stored else default


def all_settings(owner_id: str) -> dict[str, Any]:
    if _use_sql():
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            rows = session.execute(
                text("SELECT key, value_json FROM application_settings WHERE owner_id = :o"), {"o": owner_id}
            ).all()
        out = {}
        for k, v in rows:
            out[k] = v if not isinstance(v, str) else json.loads(v)
        return out
    return {}
