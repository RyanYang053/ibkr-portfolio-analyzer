from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.sql_dialect import json_cast
from app.db.state_store import postgres_available


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _tables_available() -> bool:
    if not postgres_available():
        return False
    try:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(text("SELECT 1 FROM fundamental_metric_observations LIMIT 1"))
        return True
    except SQLAlchemyError:
        return False


def persist_fundamental_metric_observation(
    *,
    symbol: str,
    metric: str,
    as_of_date: date,
    period_start: date | None,
    period_end: date | None,
    value: float,
    unit: str,
    derivation: str,
    source_observation_ids: list[str],
    source_hash: str,
    calculation_version: str,
) -> None:
    if not _tables_available():
        return

    from app.db.session import SessionLocal

    with SessionLocal() as session:
        session.execute(
            text(
                f"""
                INSERT INTO fundamental_metric_observations (
                    symbol, metric, as_of_date, period_start, period_end,
                    value, unit, derivation, source_observation_ids,
                    source_hash, calculation_version, created_at
                ) VALUES (
                    :symbol, :metric, :as_of_date, :period_start, :period_end,
                    :value, :unit, :derivation, {json_cast("source_observation_ids")},
                    :source_hash, :calculation_version, :created_at
                )
                """
            ),
            {
                "symbol": symbol.upper(),
                "metric": metric,
                "as_of_date": as_of_date,
                "period_start": period_start,
                "period_end": period_end,
                "value": value,
                "unit": unit,
                "derivation": derivation,
                "source_observation_ids": json.dumps(source_observation_ids),
                "source_hash": source_hash,
                "calculation_version": calculation_version,
                "created_at": _utc_now(),
            },
        )
        session.commit()


def read_metric_observations(symbol: str, metric: str, *, as_of: date | None = None) -> list[dict[str, Any]]:
    if not _tables_available():
        return []

    from app.db.session import SessionLocal

    query = """
        SELECT symbol, metric, as_of_date, period_start, period_end, value, unit,
               derivation, source_observation_ids, source_hash, calculation_version, created_at
        FROM fundamental_metric_observations
        WHERE symbol = :symbol AND metric = :metric
    """
    params: dict[str, Any] = {"symbol": symbol.upper(), "metric": metric}
    if as_of is not None:
        query += " AND as_of_date <= :as_of"
        params["as_of"] = as_of
    query += " ORDER BY as_of_date DESC, created_at DESC"

    with SessionLocal() as session:
        rows = session.execute(text(query), params).mappings().all()
    return [dict(row) for row in rows]
