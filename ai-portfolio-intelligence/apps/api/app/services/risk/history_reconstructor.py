from __future__ import annotations

import math
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Any, Optional

from app.schemas.domain import AccountSummary, Position
from app.services.market_data.mock_provider import MockMarketDataProvider


def get_underlying_symbol(symbol: str) -> str:
    match = re.match(r"^([A-Za-z]+)", symbol.strip())
    return match.group(1).upper() if match else symbol.upper()


def fetch_symbol_history_safe(
    provider: MockMarketDataProvider,
    symbol: str,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    try:
        return provider.get_historical_prices(symbol, start_date, end_date, total_return=True)
    except Exception:
        return []


def _valid_series(rows: list[dict[str, Any]]) -> dict[str, float]:
    series: dict[str, float] = {}
    for row in rows:
        try:
            value = float(row["close"])
            day = str(row["date"])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(value) and value > 0:
            series[day] = value
    return series


def reconstruct_portfolio_history(
    positions: list[Position],
    summary: AccountSummary,
    allow_mock: Optional[bool] = None,
) -> Optional[dict[str, Any]]:
    """Build an ex-ante *current-holdings* risk model, not account history.

    Current base-currency market values are backcast using each security's total-
    return price ratio. This avoids option multipliers and native-currency notional
    errors from ``quantity * price``. Derivatives are excluded because an underlying
    price ratio is not a valid historical option valuation model.
    """
    provider = MockMarketDataProvider(allow_mock=allow_mock)
    end_date = date.today()
    start_date = end_date - timedelta(days=400)

    spy_series = _valid_series(fetch_symbol_history_safe(provider, "SPY", start_date, end_date))
    if len(spy_series) < 2:
        return None
    qqq_series = _valid_series(fetch_symbol_history_safe(provider, "QQQ", start_date, end_date))

    from app.services.broker.ibkr_readonly import get_exchange_rate

    eligible: list[tuple[Position, float]] = []
    excluded_symbols: list[str] = []
    total_gross_value = 0.0
    for position in positions:
        if position.quantity == 0:
            continue
        try:
            base_value = float(position.market_value) * float(
                get_exchange_rate(position.currency, summary.base_currency)
            )
        except Exception:
            excluded_symbols.append(position.symbol)
            continue
        total_gross_value += abs(base_value)
        if position.asset_class in {"OPT", "FOP"}:
            excluded_symbols.append(position.symbol)
            continue
        eligible.append((position, base_value))

    if not eligible:
        return None

    histories: dict[str, dict[str, float]] = {}
    with ThreadPoolExecutor(max_workers=min(len(eligible), 10)) as executor:
        futures = {
            position.symbol: executor.submit(
                fetch_symbol_history_safe,
                provider,
                position.symbol,
                start_date,
                end_date,
            )
            for position, _ in eligible
        }
        for symbol, future in futures.items():
            histories[symbol] = _valid_series(future.result())

    included: list[tuple[Position, float]] = []
    common_dates = set(spy_series)
    modeled_gross_value = 0.0
    for position, base_value in eligible:
        series = histories.get(position.symbol, {})
        if len(series) < 2:
            excluded_symbols.append(position.symbol)
            continue
        included.append((position, base_value))
        modeled_gross_value += abs(base_value)
        common_dates &= set(series)

    if not included or len(common_dates) < 20:
        return None

    trading_dates = sorted(common_dates)
    if qqq_series:
        qqq_dates = [day for day in trading_dates if day in qqq_series]
    else:
        qqq_dates = []

    position_price_series: dict[str, list[float]] = {}
    position_value_series: dict[str, list[float]] = {}
    for position, current_base_value in included:
        series = histories[position.symbol]
        prices = [series[day] for day in trading_dates]
        latest_price = prices[-1]
        values = [current_base_value * (price / latest_price) for price in prices]
        position_price_series[position.symbol] = prices
        position_value_series[position.symbol] = values

    # Cash is held constant only for this current-allocation risk model. The output
    # must never be represented as the account's realized historical performance.
    portfolio_nav = [
        float(summary.cash)
        + sum(position_value_series[position.symbol][index] for position, _ in included)
        for index in range(len(trading_dates))
    ]

    def returns(values: list[float]) -> list[float]:
        result: list[float] = []
        for previous, current in zip(values, values[1:]):
            result.append(current / previous - 1.0 if previous > 0 else 0.0)
        return result

    port_returns = returns(portfolio_nav)
    spy_returns = returns([spy_series[day] for day in trading_dates])

    qqq_returns: list[float] = []
    if len(qqq_dates) == len(trading_dates):
        qqq_returns = returns([qqq_series[day] for day in trading_dates])

    asset_returns = {
        position.symbol: returns(position_price_series[position.symbol])
        for position, _ in included
    }

    coverage_percent = modeled_gross_value / total_gross_value * 100.0 if total_gross_value > 0 else 0.0
    return {
        "trading_dates": trading_dates,
        "portfolio_nav": portfolio_nav,
        "port_returns": port_returns,
        "spy_returns": spy_returns,
        "qqq_returns": qqq_returns,
        "asset_returns": asset_returns,
        "modeled_symbols": [position.symbol for position, _ in included],
        "excluded_symbols": sorted(set(excluded_symbols)),
        "modeled_gross_coverage_percent": round(coverage_percent, 2),
        "methodology": (
            "Ex-ante current-holdings model: today's base-currency position values are backcast by total-return "
            "price ratios. It is suitable for covariance diagnostics, not realized portfolio performance."
        ),
    }


def calculate_covariance(x: list[float], y: list[float]) -> float:
    if len(x) < 2 or len(x) != len(y):
        return 0.0
    mean_x = sum(x) / len(x)
    mean_y = sum(y) / len(y)
    return sum((x_i - mean_x) * (y_i - mean_y) for x_i, y_i in zip(x, y)) / (len(x) - 1)


def calculate_variance(x: list[float]) -> float:
    return calculate_covariance(x, x)


def calculate_correlation(x: list[float], y: list[float]) -> float:
    var_x = calculate_variance(x)
    var_y = calculate_variance(y)
    if var_x <= 0 or var_y <= 0:
        return 0.0
    return calculate_covariance(x, y) / math.sqrt(var_x * var_y)
