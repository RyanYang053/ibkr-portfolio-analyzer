from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.postgres_guard import require_postgres_persistence, require_postgres_read
from app.db.state_store import get_state_store, postgres_available
from app.schemas.domain import AccountSummary, Position
from app.services.portfolio.instrument_identity import instrument_key_from_position


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _table_available() -> bool:
    if not postgres_available():
        return False
    try:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(text("SELECT 1 FROM portfolio_snapshots LIMIT 1"))
        return True
    except SQLAlchemyError:
        return False


def _json_snapshot_key(account_id: str, business_date: date, observed_at: datetime) -> str:
    return f"{account_id}:{business_date.isoformat()}:{observed_at.isoformat()}"


def persist_portfolio_snapshot(
    account_id: str,
    business_date: date,
    summary: AccountSummary,
    positions: list[Position],
    *,
    source: str,
    source_batch_id: str | None = None,
    observed_at: datetime | None = None,
) -> str:
    snapshot_id = str(uuid.uuid4())
    observed = observed_at or _utc_now()
    rows = [
        {
            "instrument_key": instrument_key_from_position(position),
            "con_id": position.con_id,
            "symbol": position.symbol.upper(),
            "local_symbol": position.local_symbol,
            "asset_class": position.asset_class,
            "currency": position.currency,
            "quantity": float(position.quantity),
            "multiplier": float(position.multiplier),
            "local_price": float(position.market_price),
            "local_market_value": float(position.market_value),
            "fx_rate_to_base": None,
            "base_market_value": None,
            "price_source": position.price_source,
            "fx_source": None,
            "valuation_status": "available",
        }
        for position in positions
        if position.quantity != 0
    ]
    payload = {
        "id": snapshot_id,
        "account_id": account_id,
        "business_date": business_date.isoformat(),
        "observed_at": observed.isoformat(),
        "reporting_currency": summary.base_currency,
        "net_liquidation": float(summary.net_liquidation),
        "cash": float(summary.cash),
        "source": source,
        "source_batch_id": source_batch_id,
        "rows": rows,
    }

    if settings.persistence_backend != "postgres":
        store = get_state_store()
        store.write_json("portfolio_snapshots", _json_snapshot_key(account_id, business_date, observed), payload)
        return snapshot_id

    require_postgres_persistence("portfolio snapshot write", table_available=_table_available())
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        session.execute(
            text(
                """
                INSERT INTO portfolio_snapshots (
                    id, account_id, business_date, observed_at, reporting_currency,
                    net_liquidation, cash, source, source_batch_id
                ) VALUES (
                    :id, :account_id, :business_date, :observed_at, :reporting_currency,
                    :net_liquidation, :cash, :source, :source_batch_id
                )
                """
            ),
            {
                "id": snapshot_id,
                "account_id": account_id,
                "business_date": business_date,
                "observed_at": observed,
                "reporting_currency": summary.base_currency,
                "net_liquidation": Decimal(str(summary.net_liquidation)),
                "cash": Decimal(str(summary.cash)),
                "source": source,
                "source_batch_id": source_batch_id,
            },
        )
        for row in rows:
            session.execute(
                text(
                    """
                    INSERT INTO position_snapshot_rows (
                        portfolio_snapshot_id, account_id, instrument_key, con_id, symbol, local_symbol,
                        asset_class, currency, quantity, multiplier, local_price, local_market_value,
                        fx_rate_to_base, base_market_value, price_source, fx_source, valuation_status
                    ) VALUES (
                        :portfolio_snapshot_id, :account_id, :instrument_key, :con_id, :symbol, :local_symbol,
                        :asset_class, :currency, :quantity, :multiplier, :local_price, :local_market_value,
                        :fx_rate_to_base, :base_market_value, :price_source, :fx_source, :valuation_status
                    )
                    """
                ),
                {
                    "portfolio_snapshot_id": snapshot_id,
                    "account_id": account_id,
                    **row,
                    "quantity": Decimal(str(row["quantity"])),
                    "multiplier": Decimal(str(row["multiplier"])),
                    "local_price": Decimal(str(row["local_price"])) if row["local_price"] is not None else None,
                    "local_market_value": Decimal(str(row["local_market_value"])) if row["local_market_value"] is not None else None,
                },
            )
        session.commit()
    return snapshot_id


def list_snapshot_ids_for_business_dates(account_id: str, business_dates: list[date]) -> list[str]:
    if not business_dates:
        return []
    if settings.persistence_backend != "postgres":
        return []

    if not _table_available():
        return []
    require_postgres_read("portfolio snapshot read", table_available=True)
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        rows = session.execute(
            text(
                """
                SELECT id::text
                FROM portfolio_snapshots
                WHERE account_id = :account_id
                  AND business_date = ANY(:business_dates)
                ORDER BY observed_at ASC
                """
            ),
            {"account_id": account_id, "business_dates": business_dates},
        ).fetchall()
    return [row[0] for row in rows]


def link_calculation_run_snapshots(run_id: str, snapshot_ids: list[str]) -> None:
    if not snapshot_ids:
        return
    if settings.persistence_backend != "postgres" or not _table_available():
        return
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        for snapshot_id in snapshot_ids:
            session.execute(
                text(
                    """
                    INSERT INTO calculation_run_snapshots (calculation_run_id, portfolio_snapshot_id)
                    VALUES (:run_id, :snapshot_id)
                    ON CONFLICT DO NOTHING
                    """
                ),
                {"run_id": run_id, "snapshot_id": snapshot_id},
            )
        session.commit()


def link_calculation_run_transaction_batches(run_id: str, batch_ids: list[str]) -> None:
    if not batch_ids or settings.persistence_backend != "postgres" or not _table_available():
        return
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        for batch_id in batch_ids:
            session.execute(
                text(
                    """
                    INSERT INTO calculation_run_transaction_batches (calculation_run_id, batch_id)
                    VALUES (:run_id, :batch_id)
                    ON CONFLICT DO NOTHING
                    """
                ),
                {"run_id": run_id, "batch_id": batch_id},
            )
        session.commit()
