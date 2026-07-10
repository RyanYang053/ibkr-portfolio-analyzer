from __future__ import annotations

import math
from datetime import date, timedelta
from statistics import fmean
from typing import Any

FACTOR_PROXIES = {
    "Growth": "QQQ",
    "Value": "VLUE",
    "Momentum": "MTUM",
    "Low Volatility": "USMV",
}
MIN_FACTOR_OBSERVATIONS = 20


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


def _matrix_ols(y: list[float], factors: list[list[float]]) -> tuple[list[float], float | None, float | None]:
    if len(y) < MIN_FACTOR_OBSERVATIONS or not factors or len(factors[0]) != len(y):
        return [], None, None

    count = len(factors)
    length = len(y)
    augmented = []
    for row_index in range(length):
        augmented.append([1.0, *[factor[row_index] for factor in factors], y[row_index]])

    size = count + 1
    normal = [[0.0 for _ in range(size + 1)] for _ in range(size + 1)]
    for row in augmented:
        for i in range(size + 1):
            for j in range(size + 1):
                normal[i][j] += row[i] * row[j]

    for pivot in range(size):
        diag = normal[pivot][pivot]
        if abs(diag) < 1e-12:
            return [], None, None
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

    coefficients = [normal[index][size] for index in range(size)]
    fitted = []
    for row_index in range(length):
        prediction = coefficients[0]
        for factor_index, factor in enumerate(factors):
            prediction += coefficients[factor_index + 1] * factor[row_index]
        fitted.append(prediction)

    y_mean = fmean(y)
    ss_tot = sum((value - y_mean) ** 2 for value in y)
    ss_res = sum((actual - predicted) ** 2 for actual, predicted in zip(y, fitted))
    r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else None
    residual_std = math.sqrt(ss_res / max(length - size - 1, 1)) if length > size + 1 else None
    return coefficients, r_squared, residual_std


def compute_measured_factor_exposures(
    portfolio_returns_by_date: dict[str, float],
    *,
    end_date: date | None = None,
    allow_mock: bool = False,
) -> tuple[dict[str, float], str, dict[str, Any]]:
    if len(portfolio_returns_by_date) < MIN_FACTOR_OBSERVATIONS:
        return {}, "insufficient_history", {}

    history_end = end_date or max(date.fromisoformat(day) for day in portfolio_returns_by_date)
    start_date = history_end - timedelta(days=500)
    symbols = ["SPY", *FACTOR_PROXIES.values()]
    series = _fetch_factor_return_series(symbols, start_date, history_end, allow_mock=allow_mock)

    common_dates = sorted(set(portfolio_returns_by_date) & set(series["SPY"]))
    for symbol in symbols[1:]:
        common_dates = sorted(set(common_dates) & set(series[symbol]))
    if len(common_dates) < MIN_FACTOR_OBSERVATIONS:
        return {}, "insufficient_factor_history", {}

    aligned_portfolio = [portfolio_returns_by_date[day] for day in common_dates]
    spy = [series["SPY"][day] for day in common_dates]
    factor_names = ["Market", *FACTOR_PROXIES.keys()]
    factor_matrix = [[series["SPY"][day] for day in common_dates]]
    for name in FACTOR_PROXIES:
        proxy = FACTOR_PROXIES[name]
        factor_matrix.append(
            [series[proxy][day] - series["SPY"][day] for day in common_dates]
        )

    coefficients, r_squared, residual_std = _matrix_ols(aligned_portfolio, factor_matrix)
    if not coefficients:
        return {}, "regression_failed", {}

    exposures = {
        name: round(coefficients[index + 1], 4)
        for index, name in enumerate(factor_names)
        if math.isfinite(coefficients[index + 1])
    }
    if not exposures:
        return {}, "regression_failed", {}

    metadata = {
        "observation_count": len(common_dates),
        "r_squared": round(r_squared, 4) if r_squared is not None else None,
        "residual_volatility": round(residual_std, 6) if residual_std is not None else None,
        "history_end": history_end.isoformat(),
    }
    return exposures, "experimental", metadata
