"""Market/reference data persistence (plan §17: price_bars, quotes, corporate_actions, catalysts).

Populated from existing data sources (Yahoo chart, catalyst calendar, transaction-
derived corporate actions). All writes are best-effort and never block a read path.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.db.sql_dialect import json_cast


def _use_sql() -> bool:
    return settings.persistence_backend in {"postgres", "sqlite"}


def save_price_bars(instrument_id: str, interval: str, bars: list[dict[str, Any]]) -> int:
    """Upsert OHLC bars. Returns the number persisted (0 if not SQL-backed)."""
    if not _use_sql() or not bars:
        return 0
    from sqlalchemy import text

    from app.db.session import SessionLocal

    count = 0
    try:
        with SessionLocal() as session:
            for bar in bars:
                bar_date = str(bar.get("date") or bar.get("bar_date") or "")
                if not bar_date:
                    continue
                session.execute(
                    text(
                        f"""
                        INSERT INTO price_bars (instrument_id, bar_date, interval, payload_json)
                        VALUES (:iid, :bar_date, :interval, {json_cast("payload_json")})
                        ON CONFLICT(instrument_id, bar_date, interval) DO UPDATE SET payload_json = excluded.payload_json
                        """
                    ),
                    {"iid": instrument_id, "bar_date": bar_date, "interval": interval, "payload_json": json.dumps(bar)},
                )
                count += 1
            session.commit()
    except Exception:  # noqa: BLE001 — reference persistence must not break reads
        return 0
    return count


def save_quote(instrument_id: str, quote: dict[str, Any]) -> bool:
    if not _use_sql():
        return False
    from sqlalchemy import text

    from app.db.session import SessionLocal

    now = datetime.now(timezone.utc)
    try:
        with SessionLocal() as session:
            session.execute(
                text(
                    f"""
                    INSERT INTO quotes (instrument_id, as_of, payload_json)
                    VALUES (:iid, :as_of, {json_cast("payload_json")})
                    ON CONFLICT(instrument_id, as_of) DO UPDATE SET payload_json = excluded.payload_json
                    """
                ),
                {"iid": instrument_id, "as_of": now, "payload_json": json.dumps(quote)},
            )
            session.commit()
    except Exception:  # noqa: BLE001
        return False
    return True


def save_catalyst(catalyst_id: str, instrument_id: str, catalyst_type: str, payload: dict[str, Any]) -> bool:
    if not _use_sql():
        return False
    from sqlalchemy import text

    from app.db.session import SessionLocal

    now = datetime.now(timezone.utc)
    try:
        with SessionLocal() as session:
            session.execute(
                text(
                    f"""
                    INSERT INTO catalysts (catalyst_id, instrument_id, catalyst_type, payload_json, created_at)
                    VALUES (:cid, :iid, :ctype, {json_cast("payload_json")}, :created_at)
                    ON CONFLICT(catalyst_id) DO UPDATE SET payload_json = excluded.payload_json
                    """
                ),
                {"cid": catalyst_id, "iid": instrument_id, "ctype": catalyst_type,
                 "payload_json": json.dumps(payload), "created_at": now},
            )
            session.commit()
    except Exception:  # noqa: BLE001
        return False
    return True


def save_corporate_action(action_id: str, instrument_id: str, action_type: str, payload: dict[str, Any]) -> bool:
    if not _use_sql():
        return False
    from sqlalchemy import text

    from app.db.session import SessionLocal

    now = datetime.now(timezone.utc)
    try:
        with SessionLocal() as session:
            session.execute(
                text(
                    f"""
                    INSERT INTO corporate_actions (action_id, instrument_id, action_type, payload_json, created_at)
                    VALUES (:aid, :iid, :atype, {json_cast("payload_json")}, :created_at)
                    ON CONFLICT(action_id) DO UPDATE SET payload_json = excluded.payload_json
                    """
                ),
                {"aid": action_id, "iid": instrument_id, "atype": action_type,
                 "payload_json": json.dumps(payload), "created_at": now},
            )
            session.commit()
    except Exception:  # noqa: BLE001
        return False
    return True


def list_price_bars(instrument_id: str, interval: str, *, limit: int = 400) -> list[dict[str, Any]]:
    if not _use_sql():
        return []
    from sqlalchemy import text

    from app.db.session import SessionLocal

    with SessionLocal() as session:
        rows = session.execute(
            text(
                "SELECT payload_json FROM price_bars WHERE instrument_id = :iid AND interval = :i "
                "ORDER BY bar_date DESC LIMIT :limit"
            ),
            {"iid": instrument_id, "i": interval, "limit": limit},
        ).scalars().all()
    return [r if isinstance(r, dict) else json.loads(r) for r in rows]
