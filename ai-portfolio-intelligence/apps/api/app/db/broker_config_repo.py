from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.postgres_guard import require_postgres_persistence
from app.db.state_store import get_state_store, postgres_available

NAMESPACE = "broker"
RECORD_KEY = "runtime_config"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _table_available() -> bool:
    if not postgres_available():
        return False
    try:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(text("SELECT 1 FROM professional_state_records LIMIT 1"))
        return True
    except SQLAlchemyError:
        return False


def save_runtime_config(payload: dict[str, Any]) -> None:
    record = {**payload, "updated_at": _utc_now().isoformat()}
    if settings.persistence_backend == "postgres":
        require_postgres_persistence("broker runtime config", table_available=_table_available())
        get_state_store().write_json(NAMESPACE, RECORD_KEY, record)
        return
    get_state_store().write_json(NAMESPACE, RECORD_KEY, record)


def load_runtime_config() -> dict[str, Any] | None:
    if settings.persistence_backend == "postgres" and not _table_available():
        return None
    stored = get_state_store().read_json(NAMESPACE, RECORD_KEY, default=None)
    return stored if isinstance(stored, dict) else None


def apply_persisted_broker_config() -> bool:
    config = load_runtime_config()
    if not config:
        return False

    from app.services.broker.ibkr_readonly import configure_runtime_ibkr

    mode = config.get("mode")
    if isinstance(mode, str) and mode:
        settings.broker_mode = mode
    configure_runtime_ibkr(
        str(config.get("host", "127.0.0.1")),
        int(config.get("port", 4002)),
        int(config.get("client_id", 10)),
        config.get("account_id"),
    )
    return True
