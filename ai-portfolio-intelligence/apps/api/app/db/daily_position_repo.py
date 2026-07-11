from __future__ import annotations

import json
import math
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.postgres_guard import require_postgres_persistence, require_postgres_read
from app.db.state_store import get_state_store, postgres_available
from app.schemas.domain import Position


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _con_id_key(con_id: int | None) -> int:
    return int(con_id) if con_id is not None else -1


def _table_available() -> bool:
    if not postgres_available():
        return False
    try:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(text("SELECT 1 FROM daily_position_snapshots LIMIT 1"))
        return True
    except SQLAlchemyError:
        return False


def _resolve_position_fx(
    position: Position,
    *,
    snapshot_date: date,
    base_currency: str | None,
    fx_resolver,
) -> tuple[float | None, float | None, str | None, datetime | None, date | None, str]:
    native = (position.currency or settings.default_reporting_currency).upper()
    reporting = (base_currency or settings.default_reporting_currency).upper()
    if native == reporting:
        return 1.0, float(position.market_value), "identity", _utc_now(), snapshot_date, "available"

    if fx_resolver is None or not base_currency:
        if settings.persistence_backend == "postgres":
            raise ValueError(
                f"Historical FX resolver required for {native}/{reporting} on {snapshot_date}"
            )
        return None, None, None, None, None, "withheld"

    quote = fx_resolver(position.currency, base_currency, snapshot_date)
    if isinstance(quote, (float, int)):
        fx_rate = float(quote)
        fx_source = "legacy_float_resolver"
        fx_observed_at = _utc_now()
        fx_rate_date = snapshot_date
    else:
        fx_rate = float(quote.rate)
        fx_source = quote.source
        fx_observed_at = quote.observed_at
        fx_rate_date = quote.effective_date

    if not math.isfinite(fx_rate) or fx_rate <= 0:
        raise ValueError(
            f"Invalid historical FX rate for {native}/{reporting} on {snapshot_date}"
        )
    base_value = float(position.market_value) * fx_rate
    return fx_rate, base_value, fx_source, fx_observed_at, fx_rate_date, "available"


def upsert_daily_positions(
    account_id: str,
    snapshot_date: date,
    positions: list[Position],
    *,
    broker_batch_id: str | None = None,
    calculation_run_id: str | None = None,
    fx_resolver=None,
    base_currency: str | None = None,
    session=None,
) -> None:
    rows: list[dict[str, Any]] = []
    for position in positions:
        if position.quantity == 0:
            continue
        fx_rate, base_value, fx_source, fx_observed_at, fx_rate_date, valuation_status = _resolve_position_fx(
            position,
            snapshot_date=snapshot_date,
            base_currency=base_currency,
            fx_resolver=fx_resolver,
        )
        rows.append(
            {
                "symbol": position.symbol.upper(),
                "con_id": position.con_id,
                "con_id_key": _con_id_key(position.con_id),
                "local_symbol": position.local_symbol,
                "multiplier": float(position.multiplier or 1.0),
                "quantity": float(position.quantity),
                "market_value": float(position.market_value),
                "market_price": float(position.market_price),
                "avg_cost": float(position.avg_cost),
                "unrealized_pnl": float(position.unrealized_pnl),
                "currency": position.currency,
                "sector": position.sector,
                "asset_class": position.asset_class,
                "price_source": "broker_snapshot",
                "price_observed_at": position.updated_at.isoformat(),
                "fx_rate_to_base": fx_rate,
                "base_market_value": base_value,
                "fx_source": fx_source,
                "fx_observed_at": fx_observed_at.isoformat() if fx_observed_at else None,
                "fx_rate_date": fx_rate_date.isoformat() if fx_rate_date else None,
                "valuation_status": valuation_status,
                "broker_batch_id": broker_batch_id,
                "calculation_run_id": calculation_run_id,
            }
        )

    if settings.persistence_backend == "postgres":
        require_postgres_persistence("daily position snapshot write", table_available=_table_available())
        from app.db.session import SessionLocal

        now = _utc_now()
        target_session = session
        owns_session = target_session is None
        if owns_session:
            from app.db.session import SessionLocal

            target_session = SessionLocal()
        try:
            for row in rows:
                payload = json.dumps(row)
                observed_at = (
                    datetime.fromisoformat(row["fx_observed_at"])
                    if row.get("fx_observed_at")
                    else None
                )
                target_session.execute(
                    text(
                        """
                        INSERT INTO daily_position_snapshots (
                            account_id, snapshot_date, symbol, con_id, con_id_key, quantity, market_value,
                            market_price, avg_cost, unrealized_pnl, base_market_value, fx_rate_to_base,
                            price_source, broker_batch_id, calculation_run_id, currency, payload_json,
                            fx_source, fx_observed_at, fx_rate_date, valuation_status, created_at
                        ) VALUES (
                            :account_id, :snapshot_date, :symbol, :con_id, :con_id_key, :quantity, :market_value,
                            :market_price, :avg_cost, :unrealized_pnl, :base_market_value, :fx_rate_to_base,
                            :price_source, :broker_batch_id, :calculation_run_id, :currency, :payload_json,
                            :fx_source, :fx_observed_at, :fx_rate_date, :valuation_status, :created_at
                        )
                        ON CONFLICT ON CONSTRAINT uq_daily_position_snapshots_account_date_symbol
                        DO UPDATE SET
                            con_id = EXCLUDED.con_id,
                            quantity = EXCLUDED.quantity,
                            market_value = EXCLUDED.market_value,
                            market_price = EXCLUDED.market_price,
                            avg_cost = EXCLUDED.avg_cost,
                            unrealized_pnl = EXCLUDED.unrealized_pnl,
                            base_market_value = EXCLUDED.base_market_value,
                            fx_rate_to_base = EXCLUDED.fx_rate_to_base,
                            price_source = EXCLUDED.price_source,
                            broker_batch_id = EXCLUDED.broker_batch_id,
                            calculation_run_id = EXCLUDED.calculation_run_id,
                            currency = EXCLUDED.currency,
                            payload_json = EXCLUDED.payload_json,
                            fx_source = EXCLUDED.fx_source,
                            fx_observed_at = EXCLUDED.fx_observed_at,
                            fx_rate_date = EXCLUDED.fx_rate_date,
                            valuation_status = EXCLUDED.valuation_status,
                            created_at = EXCLUDED.created_at
                        """
                    ),
                    {
                        "account_id": account_id,
                        "snapshot_date": snapshot_date,
                        "symbol": row["symbol"],
                        "con_id": row["con_id"],
                        "con_id_key": row["con_id_key"],
                        "quantity": row["quantity"],
                        "market_value": row["market_value"],
                        "market_price": row["market_price"],
                        "avg_cost": row["avg_cost"],
                        "unrealized_pnl": row["unrealized_pnl"],
                        "base_market_value": row["base_market_value"],
                        "fx_rate_to_base": row["fx_rate_to_base"],
                        "price_source": row["price_source"],
                        "broker_batch_id": row["broker_batch_id"],
                        "calculation_run_id": row["calculation_run_id"],
                        "currency": row["currency"],
                        "payload_json": payload,
                        "fx_source": row["fx_source"],
                        "fx_observed_at": observed_at,
                        "fx_rate_date": date.fromisoformat(row["fx_rate_date"]) if row.get("fx_rate_date") else None,
                        "valuation_status": row["valuation_status"],
                        "created_at": now,
                    },
                )
            if owns_session:
                target_session.commit()
        finally:
            if owns_session:
                target_session.close()
        return

    store = get_state_store()
    store.write_json(
        "daily_position_snapshots",
        f"{account_id}:{snapshot_date.isoformat()}",
        rows,
    )


def read_daily_positions(account_id: str, snapshot_date: date) -> list[dict[str, Any]]:
    if settings.persistence_backend == "postgres":
        require_postgres_read("daily position snapshot read", table_available=_table_available())
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            result = session.execute(
                text(
                    """
                    SELECT payload_json
                    FROM daily_position_snapshots
                    WHERE account_id = :account_id AND snapshot_date = :snapshot_date
                    ORDER BY symbol ASC
                    """
                ),
                {"account_id": account_id, "snapshot_date": snapshot_date},
            ).fetchall()
        rows: list[dict[str, Any]] = []
        for item in result:
            try:
                rows.append(json.loads(item.payload_json))
            except json.JSONDecodeError:
                continue
        return rows

    payload = get_state_store().read_json(
        "daily_position_snapshots",
        f"{account_id}:{snapshot_date.isoformat()}",
        default=[],
    )
    return payload if isinstance(payload, list) else []
