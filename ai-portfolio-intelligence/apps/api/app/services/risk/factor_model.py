from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Optional

FACTOR_PROXIES = {
    "Growth": "QQQ",
    "Value": "VLUE",
    "Momentum": "MTUM",
    "Low Volatility": "USMV",
}


def _ols_betas(y: list[float], factors: list[list[float]]) -> list[float]:
    if len(y) < 20 or not factors or len(factors[0]) != len(y):
        return []
    count = len(factors)
    length = len(y)
    augmented = []
    for row_index in range(length):
        augmented.append([1.0, *[factor[row_index] for factor in factors], y[row_index]])

    normal = [[0.0 for _ in range(count + 2)] for _ in range(count + 2)]
    for row in augmented:
        for i in range(count + 2):
            for j in range(count + 2):
                normal[i][j] += row[i] * row[j]

    size = count + 1
    for pivot in range(size):
        diag = normal[pivot][pivot]
        if abs(diag) < 1e-12:
            return []
        for col in range(size + 1):
            normal[pivot][col] /= diag
        for row in range(size):
            if row == pivot:
                continue
            factor = normal[row][pivot]
            if factor == 0:
                continue
            for col in range(size + 1):
                normal[row][col] -= factor * normal[pivot][col]

    return [normal[index][size] for index in range(1, size)]


def _daily_returns_from_closes(closes: dict[str, float]) -> dict[str, float]:
    dates = sorted(closes)
    returns: dict[str, float] = {}
    for left, right in zip(dates, dates[1:]):
        prior = closes[left]
        current = closes[right]
        if prior > 0:
            returns[right] = (current / prior) - 1.0
    return returns


def _fetch_factor_return_series(
    symbols: list[str],
    start_date: date,
    end_date: date,
    allow_mock: bool,
) -> dict[str, dict[str, float]]:
    from app.services.market_data.mock_provider import MockMarketDataProvider

    provider = MockMarketDataProvider(allow_mock=allow_mock)
    result: dict[str, dict[str, float]] = {}
    for symbol in symbols:
        history = provider.get_historical_prices(symbol, start_date, end_date, total_return=True)
        closes = {str(item["date"]): float(item["close"]) for item in history if item.get("close")}
        result[symbol] = _daily_returns_from_closes(closes)
    return result


def compute_measured_factor_exposures(
    portfolio_returns: list[float],
    *,
    allow_mock: bool = False,
) -> tuple[dict[str, float], str]:
    if len(portfolio_returns) < 20:
        return {}, "insufficient_history"

    end_date = date.today()
    start_date = end_date - timedelta(days=500)
    symbols = ["SPY", *FACTOR_PROXIES.values()]
    series = _fetch_factor_return_series(symbols, start_date, end_date, allow_mock=allow_mock)

    common_dates = set(series["SPY"].keys())
    for symbol in symbols[1:]:
        common_dates &= set(series[symbol].keys())
    ordered_dates = sorted(common_dates)
    if len(ordered_dates) < 20:
        return {}, "insufficient_factor_history"

    aligned_portfolio = portfolio_returns[-len(ordered_dates) :]
    if len(aligned_portfolio) < 20:
        return {}, "insufficient_history"
    if len(aligned_portfolio) > len(ordered_dates):
        aligned_portfolio = aligned_portfolio[-len(ordered_dates) :]
    elif len(aligned_portfolio) < len(ordered_dates):
        ordered_dates = ordered_dates[-len(aligned_portfolio) :]

    spy = [series["SPY"][day] for day in ordered_dates]
    factor_names = list(FACTOR_PROXIES.keys())
    factor_matrix = []
    for name in factor_names:
        proxy = FACTOR_PROXIES[name]
        proxy_returns = [series[proxy][day] for day in ordered_dates]
        factor_matrix.append([proxy - benchmark for proxy, benchmark in zip(proxy_returns, spy)])

    betas = _ols_betas(aligned_portfolio, factor_matrix)
    if not betas:
        return {}, "regression_failed"

    exposures = {
        name: round(beta * 100.0, 2)
        for name, beta in zip(factor_names, betas)
        if math.isfinite(beta)
    }
    if not exposures:
        return {}, "regression_failed"
    return exposures, "experimental"
