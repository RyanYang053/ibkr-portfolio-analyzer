from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Callable, Optional

from app.schemas.domain import Position, Transaction
from app.services.portfolio.corporate_actions import parse_corporate_action


def _lot_key(symbol: str, con_id: int | None) -> tuple[str, int | None]:
    return (symbol.upper(), con_id)


def reconstruct_holdings_at_date(
    transactions: list[Transaction],
    as_of: date,
) -> dict[tuple[str, int | None], float]:
    from collections import deque

    holdings: dict[tuple[str, int | None], float] = defaultdict(float)
    open_lots: dict[tuple[str, int | None], deque] = defaultdict(deque)

    for txn in sorted(transactions, key=lambda item: (item.trade_date, item.symbol, item.action)):
        if txn.trade_date > as_of:
            break
        key = _lot_key(txn.symbol, txn.con_id)
        if txn.action == "buy":
            holdings[key] += abs(txn.quantity)
            open_lots[key].append(abs(txn.quantity))
        elif txn.action == "sell":
            remaining = abs(txn.quantity)
            holdings[key] = max(0.0, holdings[key] - remaining)
            while remaining > 1e-9 and open_lots[key]:
                lot_qty = open_lots[key][0]
                matched = min(remaining, lot_qty)
                lot_qty -= matched
                remaining -= matched
                if lot_qty <= 1e-9:
                    open_lots[key].popleft()
                else:
                    open_lots[key][0] = lot_qty
        elif txn.action == "corporate_action":
            action = parse_corporate_action(txn)
            if action:
                if action.action_type == "split":
                    holdings[key] *= action.ratio
                    open_lots[key] = deque(quantity * action.ratio for quantity in open_lots[key])
                elif action.action_type == "split_bonus":
                    holdings[key] *= 2.0
                    open_lots[key] = deque(quantity * 2.0 for quantity in open_lots[key])
    return {key: quantity for key, quantity in holdings.items() if quantity > 1e-9}


def _sector_for_symbol(symbol: str, positions: list[Position]) -> str:
    for position in positions:
        if position.symbol.upper() == symbol.upper():
            return position.sector or "Unknown"
    return "Unknown"


def _price_on_or_before(symbol: str, as_of: date, allow_mock: bool) -> Optional[float]:
    from app.services.market_data.mock_provider import MockMarketDataProvider

    provider = MockMarketDataProvider(allow_mock=allow_mock)
    history = provider.get_historical_prices(symbol.upper(), as_of - timedelta(days=10), as_of, total_return=True)
    closes = {str(item["date"]): float(item["close"]) for item in history if item.get("close")}
    if not closes:
        return None
    eligible = [day for day in closes if day <= as_of.isoformat()]
    if not eligible:
        return None
    return closes[sorted(eligible)[-1]]


def beginning_sector_weights(
    transactions: list[Transaction],
    positions: list[Position],
    period_start: date,
    base_currency: str,
    fx_resolver: Callable[..., float],
    *,
    allow_mock: bool = False,
) -> dict[str, float]:
    holdings = reconstruct_holdings_at_date(transactions, period_start - timedelta(days=1))
    sector_values: dict[str, float] = defaultdict(float)
    for (symbol, _), quantity in holdings.items():
        price = _price_on_or_before(symbol, period_start, allow_mock=allow_mock)
        if price is None or quantity <= 0:
            continue
        currency = next((position.currency for position in positions if position.symbol.upper() == symbol), "USD")
        try:
            rate = float(fx_resolver(currency, base_currency, period_start))
        except TypeError:
            rate = float(fx_resolver(currency, base_currency))
        sector = _sector_for_symbol(symbol, positions)
        sector_values[sector] += abs(quantity * price * rate)
    total = sum(sector_values.values())
    if total <= 0:
        return {}
    return {sector: value / total for sector, value in sector_values.items()}


def sector_returns_from_ledger(
    transactions: list[Transaction],
    positions: list[Position],
    period_start: date,
    period_end: date,
    *,
    allow_mock: bool = False,
) -> dict[str, float]:
    holdings = reconstruct_holdings_at_date(transactions, period_start - timedelta(days=1))
    sector_returns: dict[str, list[float]] = defaultdict(list)
    for (symbol, _), _quantity in holdings.items():
        start_price = _price_on_or_before(symbol, period_start, allow_mock=allow_mock)
        end_price = _price_on_or_before(symbol, period_end, allow_mock=allow_mock)
        if start_price is None or end_price is None or start_price <= 0:
            continue
        sector = _sector_for_symbol(symbol, positions)
        sector_returns[sector].append((end_price / start_price) - 1.0)
    return {
        sector: sum(values) / len(values)
        for sector, values in sector_returns.items()
        if values
    }
