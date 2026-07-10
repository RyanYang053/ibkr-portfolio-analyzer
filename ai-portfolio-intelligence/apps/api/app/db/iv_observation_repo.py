from __future__ import annotations

import json
from datetime import date, datetime, timezone

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.postgres_guard import require_postgres_persistence
from app.db.state_store import get_state_store, postgres_available


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _table_available() -> bool:
    if not postgres_available():
        return False
    try:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(text("SELECT 1 FROM iv_observations LIMIT 1"))
        return True
    except SQLAlchemyError:
        return False


def record_iv_observation(symbol: str, implied_volatility: float, *, source: str, observation_date: date | None = None) -> None:
    if implied_volatility <= 0:
        return
    active_date = observation_date or date.today()
    payload = {"symbol": symbol.upper(), "iv": implied_volatility, "source": source, "date": active_date.isoformat()}

    if settings.persistence_backend == "postgres":
        require_postgres_persistence("iv observation write", table_available=_table_available())
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(
                text(
                    """
                    INSERT INTO iv_observations (
                        symbol, observation_date, implied_volatility, source, payload_json, created_at
                    ) VALUES (
                        :symbol, :observation_date, :implied_volatility, :source, :payload_json, :created_at
                    )
                    ON CONFLICT ON CONSTRAINT uq_iv_observations_symbol_date_source
                    DO UPDATE SET
                        implied_volatility = EXCLUDED.implied_volatility,
                        payload_json = EXCLUDED.payload_json,
                        created_at = EXCLUDED.created_at
                    """
                ),
                {
                    "symbol": symbol.upper(),
                    "observation_date": active_date,
                    "implied_volatility": implied_volatility,
                    "source": source,
                    "payload_json": json.dumps(payload),
                    "created_at": _utc_now(),
                },
            )
            session.commit()
        return

    store = get_state_store()
    key = f"{symbol.upper()}:{active_date.isoformat()}:{source}"
    store.write_json("iv_observations", key, payload)


def read_iv_history(symbol: str, *, limit: int = 252) -> list[float]:
    if settings.persistence_backend == "postgres":
        from app.db.postgres_guard import require_postgres_read

        require_postgres_read("iv observation read", table_available=_table_available())
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            rows = session.execute(
                text(
                    """
                    SELECT implied_volatility
                    FROM iv_observations
                    WHERE symbol = :symbol
                    ORDER BY observation_date DESC
                    LIMIT :limit
                    """
                ),
                {"symbol": symbol.upper(), "limit": limit},
            ).fetchall()
        return [float(row.implied_volatility) for row in reversed(rows)]

    store = get_state_store()
    prefix = f"{symbol.upper()}:"
    # Json store has no prefix listing; use aggregate per symbol key.
    aggregate = store.read_json("iv_observations", symbol.upper(), default=[])
    if isinstance(aggregate, list):
        return [float(item["iv"]) for item in aggregate[-limit:] if isinstance(item, dict) and item.get("iv")]
    return []


def append_iv_history_json(symbol: str, implied_volatility: float, *, source: str) -> None:
    if settings.persistence_backend == "postgres":
        record_iv_observation(symbol, implied_volatility, source=source)
        return

    store = get_state_store()
    key = symbol.upper()
    history = store.read_json("iv_observations", key, default=[])
    if not isinstance(history, list):
        history = []
    history.append(
        {
            "iv": implied_volatility,
            "source": source,
            "date": date.today().isoformat(),
        }
    )
    store.write_json("iv_observations", key, history[-500:])


def iv_percentile(symbol: str, current_iv: float) -> float | None:
    history = read_iv_history(symbol)
    if len(history) < 20:
        return None
    below = sum(1 for value in history if value <= current_iv)
    return round(100.0 * below / len(history), 1)
