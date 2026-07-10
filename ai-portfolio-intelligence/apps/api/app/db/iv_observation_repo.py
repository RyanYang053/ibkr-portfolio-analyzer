from __future__ import annotations

import json
from datetime import date, datetime, timezone

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.postgres_guard import require_postgres_persistence, require_postgres_read
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


def record_iv_observation(
    symbol: str,
    implied_volatility: float,
    *,
    source: str,
    observation_date: date | None = None,
    option_right: str = "C",
    days_to_expiry: int | None = None,
    delta: float | None = None,
    moneyness: float | None = None,
    quote_timestamp: datetime | None = None,
) -> None:
    if implied_volatility <= 0:
        return
    active_date = observation_date or date.today()
    payload = {
        "symbol": symbol.upper(),
        "iv": implied_volatility,
        "source": source,
        "date": active_date.isoformat(),
        "option_right": option_right,
        "days_to_expiry": days_to_expiry,
        "delta": delta,
        "moneyness": moneyness,
        "quote_timestamp": quote_timestamp.isoformat() if quote_timestamp else None,
    }

    if settings.persistence_backend == "postgres":
        require_postgres_persistence("iv observation write", table_available=_table_available())
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(
                text(
                    """
                    INSERT INTO iv_observations (
                        symbol, observation_date, implied_volatility, source, payload_json, created_at,
                        option_right, days_to_expiry, delta, moneyness, quote_timestamp
                    ) VALUES (
                        :symbol, :observation_date, :implied_volatility, :source, :payload_json, :created_at,
                        :option_right, :days_to_expiry, :delta, :moneyness, :quote_timestamp
                    )
                    ON CONFLICT ON CONSTRAINT uq_iv_observations_symbol_date_source
                    DO UPDATE SET
                        implied_volatility = EXCLUDED.implied_volatility,
                        payload_json = EXCLUDED.payload_json,
                        created_at = EXCLUDED.created_at,
                        delta = EXCLUDED.delta,
                        moneyness = EXCLUDED.moneyness,
                        quote_timestamp = EXCLUDED.quote_timestamp
                    """
                ),
                {
                    "symbol": symbol.upper(),
                    "observation_date": active_date,
                    "implied_volatility": implied_volatility,
                    "source": source,
                    "payload_json": json.dumps(payload),
                    "created_at": _utc_now(),
                    "option_right": option_right,
                    "days_to_expiry": days_to_expiry,
                    "delta": delta,
                    "moneyness": moneyness,
                    "quote_timestamp": quote_timestamp,
                },
            )
            session.commit()
        return

    store = get_state_store()
    key = f"{symbol.upper()}:{active_date.isoformat()}:{source}:{option_right}:{days_to_expiry}"
    store.write_json("iv_observations", key, payload)


def read_iv_history(
    symbol: str,
    *,
    limit: int = 252,
    option_right: str | None = None,
    days_to_expiry: int | None = None,
) -> list[float]:
    if settings.persistence_backend == "postgres":
        require_postgres_read("iv observation read", table_available=_table_available())
        from app.db.session import SessionLocal

        filters = ["symbol = :symbol"]
        params: dict[str, object] = {"symbol": symbol.upper(), "limit": limit}
        if option_right is not None:
            filters.append("option_right = :option_right")
            params["option_right"] = option_right
        if days_to_expiry is not None:
            filters.append("days_to_expiry = :days_to_expiry")
            params["days_to_expiry"] = days_to_expiry
        where_clause = " AND ".join(filters)
        with SessionLocal() as session:
            rows = session.execute(
                text(
                    f"""
                    SELECT implied_volatility
                    FROM iv_observations
                    WHERE {where_clause}
                    ORDER BY observation_date DESC
                    LIMIT :limit
                    """
                ),
                params,
            ).fetchall()
        return [float(row.implied_volatility) for row in reversed(rows)]

    store = get_state_store()
    aggregate = store.read_json("iv_observations", symbol.upper(), default=[])
    if isinstance(aggregate, list):
        return [float(item["iv"]) for item in aggregate[-limit:] if isinstance(item, dict) and item.get("iv")]
    return []


def append_iv_history_json(
    symbol: str,
    implied_volatility: float,
    *,
    source: str,
    option_right: str = "C",
    days_to_expiry: int | None = None,
    delta: float | None = None,
    moneyness: float | None = None,
    quote_timestamp: datetime | None = None,
) -> None:
    if settings.persistence_backend == "postgres":
        record_iv_observation(
            symbol,
            implied_volatility,
            source=source,
            option_right=option_right,
            days_to_expiry=days_to_expiry,
            delta=delta,
            moneyness=moneyness,
            quote_timestamp=quote_timestamp,
        )
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
            "option_right": option_right,
            "days_to_expiry": days_to_expiry,
            "delta": delta,
            "moneyness": moneyness,
        }
    )
    store.write_json("iv_observations", key, history[-500:])


def iv_percentile(
    symbol: str,
    current_iv: float,
    *,
    option_right: str | None = None,
    days_to_expiry: int | None = None,
) -> float | None:
    history = read_iv_history(symbol, option_right=option_right, days_to_expiry=days_to_expiry)
    if len(history) < 20:
        return None
    below = sum(1 for value in history if value <= current_iv)
    return round(100.0 * below / len(history), 1)
