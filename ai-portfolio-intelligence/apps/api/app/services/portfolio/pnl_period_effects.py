from __future__ import annotations

from datetime import date
from typing import Callable

from app.schemas.domain import Position, Transaction
from app.services.portfolio.tax_lots import build_tax_lot_attribution
from app.services.portfolio.transaction_store import get_transactions


def _position_key(symbol: str, con_id: int | None) -> tuple[str, int | None]:
    return symbol.upper(), con_id


def compute_period_price_and_realized_effects(
    account_id: str,
    period_start: date,
    period_end: date,
    opening_positions: list[dict],
    closing_positions: list[Position],
    base_currency: str,
    fx_resolver: Callable,
) -> tuple[float | None, float | None, float | None, list[str]]:
    """Estimate period price effect from opening/closing marks and realized PnL from tax lots."""
    exclusions: list[str] = []
    opening_by_key: dict[tuple[str, int | None], dict] = {}
    for row in opening_positions:
        key = _position_key(str(row.get("symbol", "")), row.get("con_id"))
        opening_by_key[key] = row

    price_effect = 0.0
    has_opening = bool(opening_by_key)
    for position in closing_positions:
        key = _position_key(position.symbol, position.con_id)
        opening = opening_by_key.get(key)
        if opening is None:
            continue
        open_qty = float(opening.get("quantity") or 0.0)
        close_qty = float(position.quantity)
        if open_qty <= 0 or close_qty <= 0:
            continue
        open_price = float(opening.get("market_price") or opening.get("avg_cost") or 0.0)
        close_price = float(position.market_price)
        currency = str(opening.get("currency") or position.currency or base_currency)
        try:
            open_fx = 1.0 if currency.upper() == base_currency.upper() else float(fx_resolver(currency, base_currency, period_start))
            close_fx = 1.0 if currency.upper() == base_currency.upper() else float(fx_resolver(currency, base_currency, period_end))
        except (TypeError, ValueError):
            exclusions.append("fx_translation_withheld")
            return None, None, None, exclusions
        matched_qty = min(open_qty, close_qty)
        price_effect += matched_qty * (close_price * close_fx - open_price * open_fx)

    transactions = get_transactions(account_id)
    lot_report = build_tax_lot_attribution(
        account_id,
        transactions,
        reporting_currency=base_currency,
        period_start=period_start,
        period_end=period_end,
        fx_resolver=fx_resolver,
    )
    realized_total = float(lot_report.total_realized_gain_loss or 0.0)
    if lot_report.data_quality.get("status") == "unavailable":
        exclusions.append("realized_lot_attribution_withheld")

    if not has_opening:
        exclusions.append("opening_positions_unavailable")
        return None, realized_total if realized_total else None, None, exclusions

    return round(price_effect, 2), round(realized_total, 2), None, exclusions
