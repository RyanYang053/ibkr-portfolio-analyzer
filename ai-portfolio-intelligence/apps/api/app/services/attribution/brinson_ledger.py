from __future__ import annotations

from collections import defaultdict, deque
from datetime import date, timedelta
from typing import Callable, Optional

from app.schemas.domain import Position, Transaction
from app.services.portfolio.corporate_actions import parse_corporate_action


class AttributionDataIncomplete(RuntimeError):
    pass


def _lot_key(symbol: str, con_id: int | None) -> tuple[str, int | None]:
    return (symbol.upper(), con_id)


def reconstruct_holdings_at_date(
    transactions: list[Transaction],
    as_of: date,
) -> dict[tuple[str, int | None], float]:
    open_lots: dict[tuple[str, int | None], deque] = defaultdict(deque)
    holdings: dict[tuple[str, int | None], float] = defaultdict(float)

    for txn in sorted(transactions, key=lambda item: (item.trade_date, item.symbol, item.action)):
        if txn.trade_date > as_of:
            break
        key = _lot_key(txn.symbol, txn.con_id)
        if txn.action == "buy":
            quantity = abs(txn.quantity)
            holdings[key] += quantity
            if holdings[key] >= 0:
                open_lots[key].append(quantity)
            else:
                remaining = quantity
                while remaining > 1e-9 and open_lots[key]:
                    lot_qty = open_lots[key][0]
                    matched = min(remaining, lot_qty)
                    lot_qty -= matched
                    remaining -= matched
                    if lot_qty <= 1e-9:
                        open_lots[key].popleft()
                    else:
                        open_lots[key][0] = lot_qty
        elif txn.action == "sell":
            quantity = abs(txn.quantity)
            holdings[key] -= quantity
            if holdings[key] <= 0:
                remaining = quantity
                while remaining > 1e-9 and open_lots[key]:
                    lot_qty = open_lots[key][0]
                    matched = min(remaining, lot_qty)
                    lot_qty -= matched
                    remaining -= matched
                    if lot_qty <= 1e-9:
                        open_lots[key].popleft()
                    else:
                        open_lots[key][0] = lot_qty
                if remaining > 1e-9:
                    open_lots[key].appendleft(remaining)
            else:
                open_lots[key].append(quantity)
        elif txn.action == "corporate_action":
            action = parse_corporate_action(txn)
            if action:
                if action.action_type == "split":
                    holdings[key] *= action.ratio
                    open_lots[key] = deque(quantity * action.ratio for quantity in open_lots[key])
                elif action.action_type == "split_bonus":
                    holdings[key] *= 2.0
                    open_lots[key] = deque(quantity * 2.0 for quantity in open_lots[key])
    return {key: quantity for key, quantity in holdings.items() if abs(quantity) > 1e-9}


def _resolve_sector(symbol: str, con_id: int | None, positions: list[Position], as_of: date) -> str:
    from app.db.benchmark_repo import get_security_classification

    classification = get_security_classification(symbol, as_of, con_id=con_id)
    if classification is not None:
        return classification.sector
    for position in positions:
        if position.symbol.upper() == symbol.upper() and (position.con_id == con_id or con_id is None):
            return position.sector or "Unknown"
    return "Unknown"


def _resolve_currency(symbol: str, con_id: int | None, positions: list[Position], as_of: date) -> str:
    from app.db.benchmark_repo import get_security_classification

    classification = get_security_classification(symbol, as_of, con_id=con_id)
    if classification is not None:
        return classification.currency
    for position in positions:
        if position.symbol.upper() == symbol.upper() and (position.con_id == con_id or con_id is None):
            return position.currency
    return "USD"


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


def _fx_rate(
    currency: str,
    base_currency: str,
    rate_date: date,
    fx_resolver: Callable[..., float],
) -> float:
    try:
        return float(fx_resolver(currency, base_currency, rate_date))
    except (TypeError, ValueError) as exc:
        raise AttributionDataIncomplete(
            f"FX unavailable for {currency}/{base_currency} on {rate_date}"
        ) from exc


def beginning_sector_weights(
    transactions: list[Transaction],
    positions: list[Position],
    period_start: date,
    base_currency: str,
    fx_resolver: Callable[..., float],
    *,
    allow_mock: bool = False,
) -> dict[str, float]:
    from app.services.market_data.exchange_calendar import previous_trading_session

    holdings_as_of = previous_trading_session(period_start)
    holdings = reconstruct_holdings_at_date(transactions, holdings_as_of)
    sector_values: dict[str, float] = defaultdict(float)
    for (symbol, con_id), quantity in holdings.items():
        price = _price_on_or_before(symbol, period_start, allow_mock=allow_mock)
        if price is None or abs(quantity) <= 0:
            continue
        currency = _resolve_currency(symbol, con_id, positions, period_start)
        rate = _fx_rate(currency, base_currency, period_start, fx_resolver)
        sector = _resolve_sector(symbol, con_id, positions, period_start)
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
    base_currency: str = "USD",
    fx_resolver=None,
) -> dict[str, float]:
    from app.services.market_data.exchange_calendar import previous_trading_session

    holdings_as_of = previous_trading_session(period_start)
    holdings = reconstruct_holdings_at_date(transactions, holdings_as_of)
    sector_numerators: dict[str, float] = defaultdict(float)
    sector_denominators: dict[str, float] = defaultdict(float)
    for (symbol, con_id), quantity in holdings.items():
        start_price = _price_on_or_before(symbol, period_start, allow_mock=allow_mock)
        end_price = _price_on_or_before(symbol, period_end, allow_mock=allow_mock)
        if start_price is None or end_price is None or start_price <= 0 or abs(quantity) <= 0:
            continue
        currency = _resolve_currency(symbol, con_id, positions, period_start)
        rate = 1.0
        if fx_resolver is not None:
            rate = _fx_rate(currency, base_currency, period_start, fx_resolver)
        beginning_value = abs(quantity * start_price * rate)
        period_return = (end_price / start_price) - 1.0
        sector = _resolve_sector(symbol, con_id, positions, period_start)
        sector_numerators[sector] += beginning_value * period_return
        sector_denominators[sector] += beginning_value
    return {
        sector: sector_numerators[sector] / sector_denominators[sector]
        for sector in sector_numerators
        if sector_denominators[sector] > 0
    }
