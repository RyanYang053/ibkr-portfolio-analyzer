from __future__ import annotations

import json
from datetime import date, datetime, timezone

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.state_store import get_state_store, postgres_available


class BenchmarkDefinition(BaseModel):
    benchmark_id: str
    name: str
    currency: str
    source: str
    as_of_date: date


class BenchmarkConstituentWeight(BaseModel):
    benchmark_id: str
    constituent_key: str
    sector: str | None
    weight: float
    effective_date: date
    source: str
    as_of_date: date


class SecurityClassification(BaseModel):
    symbol: str
    con_id: int | None = None
    sector: str
    asset_class: str | None = None
    currency: str
    effective_date: date
    source: str
    as_of_date: date


class DailyAttributionContribution(BaseModel):
    account_id: str
    contribution_date: date
    security_contribution: float = 0.0
    income_contribution: float = 0.0
    fx_contribution: float = 0.0
    fee_contribution: float = 0.0
    tax_contribution: float = 0.0
    allocation_effect: float = 0.0
    selection_effect: float = 0.0
    interaction_effect: float = 0.0
    portfolio_return: float | None = None
    benchmark_return: float | None = None
    source: str
    as_of_date: date


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _table_available(table_name: str) -> bool:
    if not postgres_available():
        return False
    try:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(text(f"SELECT 1 FROM {table_name} LIMIT 1"))
        return True
    except SQLAlchemyError:
        return False


def _json_key(namespace: str, record_key: str) -> tuple[str, str]:
    return namespace, record_key


def upsert_benchmark_definition(record: BenchmarkDefinition) -> None:
    if postgres_available() and _table_available("benchmark_definitions"):
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(
                text(
                    """
                    INSERT INTO benchmark_definitions (
                        benchmark_id, name, currency, source, as_of_date
                    ) VALUES (
                        :benchmark_id, :name, :currency, :source, :as_of_date
                    )
                    ON CONFLICT (benchmark_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        currency = EXCLUDED.currency,
                        source = EXCLUDED.source,
                        as_of_date = EXCLUDED.as_of_date
                    """
                ),
                record.model_dump(),
            )
            session.commit()
        return
    store = get_state_store()
    store.write_json("benchmark_definitions", record.benchmark_id, record.model_dump(mode="json"))


def list_benchmark_constituent_weights(
    benchmark_id: str,
    effective_date: date,
) -> list[BenchmarkConstituentWeight]:
    if postgres_available() and _table_available("benchmark_constituent_weights"):
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            rows = session.execute(
                text(
                    """
                    SELECT benchmark_id, constituent_key, sector, weight, effective_date, source, as_of_date
                    FROM benchmark_constituent_weights
                    WHERE benchmark_id = :benchmark_id AND effective_date <= :effective_date
                    ORDER BY effective_date DESC, constituent_key
                    """
                ),
                {"benchmark_id": benchmark_id, "effective_date": effective_date},
            ).mappings()
            latest_effective: date | None = None
            results: list[BenchmarkConstituentWeight] = []
            for row in rows:
                row_date = row["effective_date"]
                if latest_effective is None:
                    latest_effective = row_date
                if row_date != latest_effective:
                    break
                results.append(
                    BenchmarkConstituentWeight(
                        benchmark_id=row["benchmark_id"],
                        constituent_key=row["constituent_key"],
                        sector=row["sector"],
                        weight=float(row["weight"]),
                        effective_date=row_date,
                        source=row["source"],
                        as_of_date=row["as_of_date"],
                    )
                )
            return results

    store = get_state_store()
    payload = store.read_json("benchmark_constituent_weights", benchmark_id, default={"weights": []})
    weights = payload.get("weights", []) if isinstance(payload, dict) else []
    return [
        BenchmarkConstituentWeight(**item)
        for item in weights
        if date.fromisoformat(str(item["effective_date"])) <= effective_date
    ]


def sector_weights_from_constituents(weights: list[BenchmarkConstituentWeight]) -> dict[str, float]:
    grouped: dict[str, float] = {}
    for row in weights:
        sector = row.sector or "Unknown"
        grouped[sector] = grouped.get(sector, 0.0) + row.weight
    total = sum(grouped.values())
    if total <= 0:
        return {}
    return {sector: value / total for sector, value in grouped.items()}


def get_security_classification(
    symbol: str,
    as_of: date,
    *,
    con_id: int | None = None,
) -> SecurityClassification | None:
    if postgres_available() and _table_available("security_classifications"):
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            row = session.execute(
                text(
                    """
                    SELECT symbol, con_id, sector, asset_class, currency, effective_date, source, as_of_date
                    FROM security_classifications
                    WHERE symbol = :symbol
                      AND effective_date <= :as_of
                      AND (:con_id IS NULL OR con_id IS NULL OR con_id = :con_id)
                    ORDER BY effective_date DESC, as_of_date DESC
                    LIMIT 1
                    """
                ),
                {"symbol": symbol.upper(), "as_of": as_of, "con_id": con_id},
            ).mappings().first()
            if row is None:
                return None
            return SecurityClassification(**dict(row))

    store = get_state_store()
    payload = store.read_json("security_classifications", symbol.upper(), default={"records": []})
    records = payload.get("records", []) if isinstance(payload, dict) else []
    eligible = [
        record
        for record in records
        if date.fromisoformat(str(record["effective_date"])) <= as_of
        and (con_id is None or record.get("con_id") in {None, con_id})
    ]
    if not eligible:
        return None
    latest = max(eligible, key=lambda item: (item["effective_date"], item.get("as_of_date", item["effective_date"])))
    return SecurityClassification(**latest)


def save_security_classification(record: SecurityClassification) -> None:
    if postgres_available() and _table_available("security_classifications"):
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(
                text(
                    """
                    INSERT INTO security_classifications (
                        symbol, con_id, sector, asset_class, currency, effective_date, source, as_of_date
                    ) VALUES (
                        :symbol, :con_id, :sector, :asset_class, :currency, :effective_date, :source, :as_of_date
                    )
                    """
                ),
                {
                    **record.model_dump(),
                    "symbol": record.symbol.upper(),
                },
            )
            session.commit()
        return
    store = get_state_store()
    key = record.symbol.upper()
    payload = store.read_json("security_classifications", key, default={"records": []})
    records = payload.get("records", []) if isinstance(payload, dict) else []
    records.append(record.model_dump(mode="json"))
    store.write_json("security_classifications", key, {"records": records})


def save_daily_attribution_contribution(record: DailyAttributionContribution) -> None:
    if postgres_available() and _table_available("daily_attribution_contributions"):
        from app.db.session import SessionLocal

        payload = record.model_dump()
        with SessionLocal() as session:
            session.execute(
                text(
                    """
                    INSERT INTO daily_attribution_contributions (
                        account_id, contribution_date,
                        security_contribution, income_contribution, fx_contribution,
                        fee_contribution, tax_contribution,
                        allocation_effect, selection_effect, interaction_effect,
                        portfolio_return, benchmark_return, source, as_of_date
                    ) VALUES (
                        :account_id, :contribution_date,
                        :security_contribution, :income_contribution, :fx_contribution,
                        :fee_contribution, :tax_contribution,
                        :allocation_effect, :selection_effect, :interaction_effect,
                        :portfolio_return, :benchmark_return, :source, :as_of_date
                    )
                    """
                ),
                payload,
            )
            session.commit()
        return
    store = get_state_store()
    key = f"{record.account_id}:{record.contribution_date.isoformat()}"
    store.write_json("daily_attribution_contributions", key, record.model_dump(mode="json"))


def list_daily_attribution_contributions(
    account_id: str,
    period_start: date,
    period_end: date,
) -> list[DailyAttributionContribution]:
    if postgres_available() and _table_available("daily_attribution_contributions"):
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            rows = session.execute(
                text(
                    """
                    SELECT account_id, contribution_date,
                           security_contribution, income_contribution, fx_contribution,
                           fee_contribution, tax_contribution,
                           allocation_effect, selection_effect, interaction_effect,
                           portfolio_return, benchmark_return, source, as_of_date
                    FROM daily_attribution_contributions
                    WHERE account_id = :account_id
                      AND contribution_date >= :period_start
                      AND contribution_date <= :period_end
                    ORDER BY contribution_date
                    """
                ),
                {
                    "account_id": account_id,
                    "period_start": period_start,
                    "period_end": period_end,
                },
            ).mappings()
            return [DailyAttributionContribution(**dict(row)) for row in rows]

    store = get_state_store()
    prefix = f"{account_id}:"
    records: list[DailyAttributionContribution] = []
    if hasattr(store, "records"):
        for key, payload in getattr(store, "records", {}).items():
            if not str(key).startswith("daily_attribution_contributions:"):
                continue
            record_key = str(key).split(":", 1)[1]
            if not record_key.startswith(prefix):
                continue
            item = payload if isinstance(payload, dict) else json.loads(payload)
            contribution_date = date.fromisoformat(str(item["contribution_date"]))
            if period_start <= contribution_date <= period_end:
                records.append(DailyAttributionContribution(**item))
    records.sort(key=lambda item: item.contribution_date)
    return records
