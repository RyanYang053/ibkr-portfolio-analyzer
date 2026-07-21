"""Shared helpers to build Decision Center context from live holdings."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.schemas.domain import Position


def _policy_max_single() -> float:
    try:
        from app.db.financial_plan_repo import FinancialPlanRepository

        plan = FinancialPlanRepository().latest()
        if plan and plan.policy and plan.policy.max_single_position_pct is not None:
            return float(plan.policy.max_single_position_pct)
    except Exception:
        pass
    return 12.0


def tax_flags_for_holding(*, account_id: str, symbol: str, con_id: int | None) -> dict[str, Any]:
    try:
        from app.db.tax_lot_snapshot_repo import list_tax_lot_snapshots

        lots = list_tax_lot_snapshots(account_id, as_of_date=date.today())
        matched = [
            lot
            for lot in lots
            if str(lot.get("symbol") or "").upper() == symbol.upper()
            and (con_id is None or lot.get("con_id") in {None, con_id})
        ]
        if matched:
            short_term = 0
            long_term = 0
            total_qty = 0.0
            for lot in matched:
                qty = float(lot.get("quantity") or 0)
                total_qty += abs(qty)
                acquired = lot.get("acquired_date")
                try:
                    acquired_date = date.fromisoformat(str(acquired)[:10]) if acquired else None
                except ValueError:
                    acquired_date = None
                if acquired_date and (date.today() - acquired_date).days >= 365:
                    long_term += 1
                else:
                    short_term += 1
            return {
                "status": "available",
                "methodology_status": "experimental",
                "lot_count": len(matched),
                "short_term_lots": short_term,
                "long_term_lots": long_term,
                "total_quantity": total_qty,
                "source": "tax_lot_snapshots",
            }
    except Exception:
        pass
    return {"status": "unknown", "methodology_status": "unknown", "lot_count": 0}


def _price_history(symbol: str, days: int = 60) -> list[dict[str, Any]]:
    try:
        import sys

        from app.core.config import settings
        from app.services.market_data.mock_provider import MockMarketDataProvider

        allow_mock = settings.broker_mode == "mock_ibkr_readonly" or "pytest" in sys.modules
        end = date.today()
        start = end - timedelta(days=days)
        return MockMarketDataProvider(allow_mock=allow_mock).get_historical_prices(symbol, start, end)
    except Exception:
        return []


def liquidity_flags_for_holding(position: Position) -> dict[str, Any]:
    volume = getattr(position, "average_daily_volume", None)
    if volume is not None:
        try:
            if float(volume) > 0:
                return {"status": "available", "average_daily_volume": float(volume), "source": "position"}
        except (TypeError, ValueError):
            pass

    history = _price_history(position.symbol)
    dollar_volumes: list[float] = []
    for row in history:
        close = row.get("close")
        shares = row.get("volume")
        if close is None or shares is None:
            continue
        try:
            shares_value = float(shares)
            close_value = float(close)
        except (TypeError, ValueError):
            continue
        if shares_value <= 0 or close_value <= 0:
            continue
        dollar_volumes.append(close_value * shares_value)

    if len(dollar_volumes) < 10:
        return {"status": "incomplete", "reason": "adv_history_insufficient", "sample_days": len(dollar_volumes)}

    median_adv = sorted(dollar_volumes)[len(dollar_volumes) // 2]
    market_value = abs(float(getattr(position, "market_value", 0) or 0))
    days_to_exit = (market_value / median_adv) if median_adv > 0 else None
    return {
        "status": "available",
        "average_daily_dollar_volume": median_adv,
        "estimated_days_to_exit_at_10pct_participation": (
            round((days_to_exit or 0) / 0.10, 2) if days_to_exit is not None else None
        ),
        "source": "price_history_median",
        "sample_days": len(dollar_volumes),
    }


def valuation_status_for_holding(symbol: str) -> str:
    try:
        from app.db.state_store import get_state_store

        store = get_state_store()
        row = store.read_json("valuation_runs", f"latest:{symbol.upper()}", default=None)
        if isinstance(row, dict) and row.get("status"):
            return str(row["status"])
    except Exception:
        pass
    return "withheld"


def build_decision_context_for_position(
    position: Position,
    *,
    account_id: str,
    thesis: dict[str, Any] | None = None,
    fundamentals: dict[str, Any] | None = None,
    risk_metrics: dict[str, Any] | None = None,
) -> Any:
    from app.services.decision_center.holding_context import build_holding_context

    instrument_key = f"{position.symbol}:{position.con_id}" if position.con_id else position.symbol
    max_single = _policy_max_single()
    weight = float(getattr(position, "portfolio_weight", 0) or 0)
    fund = fundamentals if fundamentals is not None else {"present": True}
    risk = risk_metrics if risk_metrics is not None else {"max_drawdown_decimal": -0.1}
    return build_holding_context(
        account_id=account_id,
        instrument_key=instrument_key,
        symbol=position.symbol,
        position={
            "portfolio_weight": weight,
            "weight": weight,
            "market_value": float(position.market_value),
            "quantity": float(position.quantity),
        },
        thesis=thesis or {},
        risk_metrics=risk,
        fundamentals=fund,
        liquidity=liquidity_flags_for_holding(position),
        tax_flags=tax_flags_for_holding(
            account_id=account_id,
            symbol=position.symbol,
            con_id=getattr(position, "con_id", None),
        ),
        valuation_status=valuation_status_for_holding(position.symbol),
        max_single_position_pct=max_single,
    )
