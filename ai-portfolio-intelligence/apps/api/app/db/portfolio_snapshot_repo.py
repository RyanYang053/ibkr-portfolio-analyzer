from __future__ import annotations

import json
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


def configured_snapshot_tolerance(net_liquidation: float) -> float:
    return max(
        settings.snapshot_nav_tie_out_absolute_tolerance,
        abs(net_liquidation) * settings.snapshot_nav_tie_out_tolerance_bps / 10_000.0,
    )


def _valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, TypeError):
        return False


def persist_portfolio_snapshot(
    account_id: str,
    business_date: date,
    summary: AccountSummary,
    positions: list[Position],
    *,
    source: str,
    fx_quote_resolver,
    source_batch_id: str | None = None,
    observed_at: datetime | None = None,
    designate_eod: bool = True,
    session=None,
    snapshot_id: str | None = None,
) -> str:
    snapshot_id = snapshot_id or str(uuid.uuid4())
    observed = observed_at or _utc_now()
    rows: list[dict[str, Any]] = []
    gross_local_count = 0
    valued_count = 0

    for position in positions:
        if position.quantity == 0:
            continue
        gross_local_count += 1

        quote = fx_quote_resolver(position.currency, summary.base_currency, business_date)
        if isinstance(quote, (float, int)):
            fx_rate = float(quote)
            fx_source = "legacy_float_resolver"
            fx_observed_at = observed
            fx_rate_date = business_date
        else:
            fx_rate = float(quote.rate)
            fx_source = quote.source
            fx_observed_at = quote.observed_at
            fx_rate_date = quote.effective_date
        base_market_value = float(position.market_value) * fx_rate
        valued_count += 1

        rows.append(
            {
                "instrument_key": instrument_key_from_position(position),
                "con_id": position.con_id,
                "symbol": position.symbol.upper(),
                "local_symbol": position.local_symbol,
                "asset_class": position.asset_class,
                "currency": position.currency,
                "quantity": float(position.quantity),
                "multiplier": float(position.multiplier or 1.0),
                "local_price": float(position.market_price),
                "local_market_value": float(position.market_value),
                "fx_rate_to_base": fx_rate,
                "base_market_value": base_market_value,
                "price_source": position.price_source,
                "price_observed_at": position.updated_at,
                "fx_source": fx_source,
                "fx_observed_at": fx_observed_at,
                "fx_rate_date": fx_rate_date,
                "valuation_status": "available",
            }
        )

    coverage = valued_count / gross_local_count if gross_local_count else 1.0
    position_value = sum(row["base_market_value"] for row in rows)
    tie_out = float(summary.net_liquidation) - float(summary.cash) - position_value
    tolerance = configured_snapshot_tolerance(float(summary.net_liquidation))
    status = (
        "complete"
        if coverage == 1.0 and abs(tie_out) <= tolerance
        else "partial"
    )
    completeness = {
        "gross_local_count": gross_local_count,
        "valued_count": valued_count,
        "coverage": coverage,
        "position_value": position_value,
        "tie_out_tolerance": tolerance,
    }

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
        "snapshot_status": status,
        "completeness_json": completeness,
        "valuation_coverage_percent": coverage,
        "broker_nav_tie_out": tie_out,
        "is_designated_eod": designate_eod,
        "rows": rows,
    }

    if settings.persistence_backend != "postgres":
        store = get_state_store()
        store.write_json("portfolio_snapshots", _json_snapshot_key(account_id, business_date, observed), payload)
        return snapshot_id

    require_postgres_persistence("portfolio snapshot write", table_available=_table_available())
    from app.db.session import SessionLocal

    def _write_postgres_snapshot(db_session) -> None:
        if designate_eod:
            db_session.execute(
                text(
                    """
                    UPDATE portfolio_snapshots
                    SET is_designated_eod = FALSE
                    WHERE account_id = :account_id AND business_date = :business_date
                    """
                ),
                {"account_id": account_id, "business_date": business_date},
            )
        db_session.execute(
            text(
                """
                INSERT INTO portfolio_snapshots (
                    id, account_id, business_date, observed_at, reporting_currency,
                    net_liquidation, cash, source, source_batch_id,
                    snapshot_status, completeness_json, valuation_coverage_percent,
                    broker_nav_tie_out, is_designated_eod
                ) VALUES (
                    :id, :account_id, :business_date, :observed_at, :reporting_currency,
                    :net_liquidation, :cash, :source, :source_batch_id,
                    :snapshot_status, :completeness_json, :valuation_coverage_percent,
                    :broker_nav_tie_out, :is_designated_eod
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
                "snapshot_status": status,
                "completeness_json": json.dumps(completeness),
                "valuation_coverage_percent": Decimal(str(coverage)),
                "broker_nav_tie_out": Decimal(str(tie_out)),
                "is_designated_eod": designate_eod,
            },
        )
        for row in rows:
            db_session.execute(
                text(
                    """
                    INSERT INTO position_snapshot_rows (
                        portfolio_snapshot_id, account_id, instrument_key, con_id, symbol, local_symbol,
                        asset_class, currency, quantity, multiplier, local_price, local_market_value,
                        fx_rate_to_base, base_market_value, price_source, fx_source, valuation_status,
                        price_observed_at, fx_observed_at, fx_rate_date
                    ) VALUES (
                        :portfolio_snapshot_id, :account_id, :instrument_key, :con_id, :symbol, :local_symbol,
                        :asset_class, :currency, :quantity, :multiplier, :local_price, :local_market_value,
                        :fx_rate_to_base, :base_market_value, :price_source, :fx_source, :valuation_status,
                        :price_observed_at, :fx_observed_at, :fx_rate_date
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
                    "fx_rate_to_base": Decimal(str(row["fx_rate_to_base"])) if row["fx_rate_to_base"] is not None else None,
                    "base_market_value": Decimal(str(row["base_market_value"])) if row["base_market_value"] is not None else None,
                },
            )

    if session is not None:
        _write_postgres_snapshot(session)
        return snapshot_id

    with SessionLocal() as standalone_session:
        _write_postgres_snapshot(standalone_session)
        standalone_session.commit()
    return snapshot_id


def read_portfolio_snapshot(snapshot_id: str) -> dict[str, Any]:
    if settings.persistence_backend != "postgres":
        raise ValueError("portfolio snapshot read requires postgres persistence")
    require_postgres_read("portfolio snapshot read", table_available=_table_available())
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        row = session.execute(
            text("SELECT * FROM portfolio_snapshots WHERE id = :id"),
            {"id": snapshot_id},
        ).mappings().first()
    if row is None:
        raise ValueError(f"snapshot not found: {snapshot_id}")
    return dict(row)


def read_designated_eod_snapshot(account_id: str, business_date: date) -> dict[str, Any] | None:
    if settings.persistence_backend != "postgres":
        return None
    if not _table_available():
        return None
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        row = session.execute(
            text(
                """
                SELECT * FROM portfolio_snapshots
                WHERE account_id = :account_id
                  AND business_date = :business_date
                  AND is_designated_eod = TRUE
                ORDER BY observed_at DESC
                LIMIT 1
                """
            ),
            {"account_id": account_id, "business_date": business_date},
        ).mappings().first()
    return dict(row) if row else None


def read_position_rows(snapshot_id: str) -> list[dict[str, Any]]:
    if settings.persistence_backend != "postgres":
        return []
    if not _table_available():
        return []
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        rows = session.execute(
            text(
                """
                SELECT instrument_key, con_id, symbol, local_symbol, asset_class, currency,
                       quantity, multiplier, local_price, local_market_value,
                       fx_rate_to_base, base_market_value, price_source, fx_source,
                       valuation_status, price_observed_at, fx_observed_at, fx_rate_date
                FROM position_snapshot_rows
                WHERE portfolio_snapshot_id = :snapshot_id
                ORDER BY symbol ASC
                """
            ),
            {"snapshot_id": snapshot_id},
        ).mappings().all()
    return [dict(row) for row in rows]


def require_complete_snapshot(account_id: str, business_date: date) -> dict[str, Any]:
    snapshot = read_designated_eod_snapshot(account_id, business_date)
    if snapshot is None:
        raise ValueError("designated EOD snapshot missing")
    if snapshot["snapshot_status"] != "complete":
        raise ValueError(f"snapshot is {snapshot['snapshot_status']}")
    return snapshot


def record_snapshot_atomic(
    *,
    account_id: str,
    business_date: date,
    summary: AccountSummary,
    positions: list[Position],
    pnl_snapshot: dict[str, Any],
    fx_quote_resolver,
    source: str = "pnl_snapshot",
    source_batch_id: str | None = None,
) -> str:
    """Atomically persist portfolio snapshot, position rows, daily positions, and PnL snapshot."""
    if settings.persistence_backend != "postgres":
        snapshot_id = persist_portfolio_snapshot(
            account_id,
            business_date,
            summary,
            positions,
            source=source,
            fx_quote_resolver=fx_quote_resolver,
            source_batch_id=source_batch_id,
        )
        from app.db.daily_position_repo import upsert_daily_positions
        from app.db.pnl_snapshot_repo import upsert_pnl_snapshot

        upsert_daily_positions(
            account_id,
            business_date,
            positions,
            base_currency=summary.base_currency,
            fx_resolver=fx_quote_resolver,
        )
        upsert_pnl_snapshot(account_id, business_date, pnl_snapshot)
        return snapshot_id

    require_postgres_persistence("atomic snapshot write", table_available=_table_available())
    from app.db.daily_position_repo import upsert_daily_positions
    from app.db.pnl_snapshot_repo import upsert_pnl_snapshot
    from app.db.session import SessionLocal

    snapshot_id = str(uuid.uuid4())
    with SessionLocal.begin() as session:
        persist_portfolio_snapshot(
            account_id,
            business_date,
            summary,
            positions,
            source=source,
            fx_quote_resolver=fx_quote_resolver,
            source_batch_id=source_batch_id,
            snapshot_id=snapshot_id,
            session=session,
        )
        upsert_daily_positions(
            account_id,
            business_date,
            positions,
            base_currency=summary.base_currency,
            fx_resolver=fx_quote_resolver,
            session=session,
        )
        upsert_pnl_snapshot(account_id, business_date, pnl_snapshot, session=session)
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
                  AND is_designated_eod = TRUE
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
            if not _valid_uuid(snapshot_id):
                continue
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
