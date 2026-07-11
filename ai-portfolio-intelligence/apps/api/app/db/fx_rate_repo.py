from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.state_store import postgres_available


@dataclass(frozen=True)
class FxRateMetadata:
    rate: float
    effective_date: date
    observed_at: datetime
    source: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _table_available() -> bool:
    if not postgres_available():
        return False
    try:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(text("SELECT 1 FROM fx_rate_observations LIMIT 1"))
        return True
    except SQLAlchemyError:
        return False


def upsert_rate_series(
    from_currency: str,
    to_currency: str,
    series: dict[str, float],
    *,
    source: str = "yahoo_fx",
) -> None:
    if not _table_available() or not series:
        return

    from app.db.session import SessionLocal

    now = _utc_now()
    with SessionLocal() as session:
        for day_text, rate in series.items():
            session.execute(
                text(
                    """
                    INSERT INTO fx_rate_observations (
                        from_currency, to_currency, observation_date, rate, source, ingested_at
                    ) VALUES (
                        :from_currency, :to_currency, :observation_date, :rate, :source, :ingested_at
                    )
                    ON CONFLICT ON CONSTRAINT uq_fx_rate_observations_pair_date
                    DO UPDATE SET
                        rate = EXCLUDED.rate,
                        source = EXCLUDED.source,
                        ingested_at = EXCLUDED.ingested_at
                    """
                ),
                {
                    "from_currency": from_currency.upper(),
                    "to_currency": to_currency.upper(),
                    "observation_date": date.fromisoformat(day_text),
                    "rate": float(rate),
                    "source": source,
                    "ingested_at": now,
                },
            )
        session.commit()


def load_rate_series(from_currency: str, to_currency: str) -> dict[str, float] | None:
    if not _table_available():
        return None

    from app.db.session import SessionLocal

    with SessionLocal() as session:
        rows = session.execute(
            text(
                """
                SELECT observation_date, rate
                FROM fx_rate_observations
                WHERE from_currency = :from_currency AND to_currency = :to_currency
                ORDER BY observation_date ASC
                """
            ),
            {
                "from_currency": from_currency.upper(),
                "to_currency": to_currency.upper(),
            },
        ).mappings().all()

    if not rows:
        return None
    return {row["observation_date"].isoformat(): float(row["rate"]) for row in rows}


def lookup_rate_with_metadata(
    from_currency: str,
    to_currency: str,
    as_of: date,
    *,
    max_staleness_days: int = 7,
) -> FxRateMetadata | None:
    if not _table_available():
        return None

    from app.db.session import SessionLocal

    with SessionLocal() as session:
        row = session.execute(
            text(
                """
                SELECT observation_date, rate, source, ingested_at
                FROM fx_rate_observations
                WHERE from_currency = :from_currency
                  AND to_currency = :to_currency
                  AND observation_date <= :as_of
                ORDER BY observation_date DESC
                LIMIT 1
                """
            ),
            {
                "from_currency": from_currency.upper(),
                "to_currency": to_currency.upper(),
                "as_of": as_of,
            },
        ).mappings().first()

    if row is None:
        return None
    effective_date = row["observation_date"]
    staleness = (as_of - effective_date).days
    if staleness > max_staleness_days:
        return None
    return FxRateMetadata(
        rate=float(row["rate"]),
        effective_date=effective_date,
        observed_at=row["ingested_at"] or _utc_now(),
        source=str(row["source"] or "postgres_fx"),
    )


def lookup_rate(
    from_currency: str,
    to_currency: str,
    as_of: date,
    *,
    max_staleness_days: int = 7,
) -> Optional[float]:
    resolved = lookup_rate_with_metadata(
        from_currency,
        to_currency,
        as_of,
        max_staleness_days=max_staleness_days,
    )
    return resolved.rate if resolved is not None else None
