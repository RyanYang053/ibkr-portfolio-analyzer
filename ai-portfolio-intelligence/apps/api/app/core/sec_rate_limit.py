from __future__ import annotations

import threading
import time

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings

_SEC_LOCK = threading.Lock()
_LAST_REQUEST_AT: float | None = None
_ADVISORY_LOCK_ID = 0x53454345444152  # "SECEDAR"


def _table_available() -> bool:
    if settings.persistence_backend != "postgres":
        return False
    try:
        from app.db.state_store import postgres_available

        if not postgres_available():
            return False
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(text("SELECT 1 FROM sec_edgar_request_gate LIMIT 1"))
        return True
    except SQLAlchemyError:
        return False


def _postgres_throttle() -> None:
    min_interval = 1.0 / max(settings.sec_edgar_requests_per_second, 0.1)
    from app.db.session import SessionLocal

    with SessionLocal.begin() as session:
        session.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": _ADVISORY_LOCK_ID})
        row = session.execute(
            text(
                """
                SELECT EXTRACT(EPOCH FROM last_request_at)::float AS last_epoch
                FROM sec_edgar_request_gate
                WHERE id = 1
                FOR UPDATE
                """
            )
        ).mappings().first()
        now = time.time()
        last_epoch = float(row["last_epoch"]) if row and row.get("last_epoch") is not None else 0.0
        elapsed = now - last_epoch
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        session.execute(
            text(
                """
                UPDATE sec_edgar_request_gate
                SET last_request_at = NOW()
                WHERE id = 1
                """
            )
        )


def _local_throttle() -> None:
    global _LAST_REQUEST_AT
    min_interval = 1.0 / max(settings.sec_edgar_requests_per_second, 0.1)
    with _SEC_LOCK:
        now = time.monotonic()
        if _LAST_REQUEST_AT is not None:
            elapsed = now - _LAST_REQUEST_AT
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
        _LAST_REQUEST_AT = time.monotonic()


def throttle_sec_edgar_request() -> None:
    """Serialize SEC EDGAR requests across workers when postgres gate is available."""
    if settings.persistence_backend == "postgres" and _table_available():
        _postgres_throttle()
        return
    _local_throttle()
