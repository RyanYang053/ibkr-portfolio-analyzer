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
MIN_FACTOR_OBSERVATIONS = 126


def _daily_returns_from_closes(closes: dict[str, float]) -> dict[str, float]:
    dates = sorted(closes)
    returns: dict[str, float] = {}
    for left, right in zip(dates, dates[1:], strict=False):
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


def _matrix_ols(
    y: list[float],
    factors: list[list[float]],
    *,
    min_observations: int | None = None,
) -> tuple[list[float], float | None, float | None, dict[str, Any]]:
    required = min_observations if min_observations is not None else MIN_FACTOR_OBSERVATIONS
    if len(y) < required or not factors or len(factors[0]) != len(y):
        return [], None, None, {}

    count = len(factors)
    length = len(y)
    design = [[1.0, *[factor[row_index] for factor in factors]] for row_index in range(length)]

    size = count + 1
    normal = [[0.0 for _ in range(size)] for _ in range(size)]
    xty = [0.0 for _ in range(size)]
    for row_index, row in enumerate(design):
        target = y[row_index]
        for i in range(size):
            xty[i] += row[i] * target
            for j in range(size):
                normal[i][j] += row[i] * row[j]

    inverse = [[0.0 for _ in range(size)] for _ in range(size)]
    augmented = [normal[row][:] + [1.0 if index == row else 0.0 for index in range(size)] for row in range(size)]
    for pivot in range(size):
        diag = augmented[pivot][pivot]
        if abs(diag) < 1e-12:
            return [], None, None, {}
        for col in range(2 * size):
            augmented[pivot][col] /= diag
        for row in range(size):
            if row == pivot:
                continue
            factor = augmented[row][pivot]
            if factor == 0:
                continue
            for col in range(2 * size):
                augmented[row][col] -= factor * augmented[pivot][col]
    inverse = [row[size:] for row in augmented]
    coefficients = [sum(inverse[index][col] * xty[col] for col in range(size)) for index in range(size)]

    fitted = []
    for row in design:
        prediction = sum(coeff * value for coeff, value in zip(coefficients, row, strict=False))
        fitted.append(prediction)

    y_mean = fmean(y)
    ss_tot = sum((value - y_mean) ** 2 for value in y)
    ss_res = sum((actual - predicted) ** 2 for actual, predicted in zip(y, fitted, strict=False))
    r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else None
    dof = max(length - size, 1)
    residual_std = math.sqrt(ss_res / dof) if length > size else None

    diagnostics: dict[str, Any] = {
        "model_label": "ETF-proxy exposure model",
        "observation_count": length,
        "r_squared": round(r_squared, 4) if r_squared is not None else None,
        "adjusted_r_squared": (
            round(1.0 - (1.0 - r_squared) * (length - 1) / max(length - size - 1, 1), 4)
            if r_squared is not None and length > size + 1
            else None
        ),
        "residual_volatility": round(residual_std, 6) if residual_std is not None else None,
    }

    condition_number = None
    try:
        import numpy as np

        normal_array = np.array(normal, dtype=float)
        condition_number = float(np.linalg.cond(normal_array))
    except Exception:
        max_diag = max(abs(normal[i][i]) for i in range(size)) or 1.0
        min_diag = min(abs(normal[i][i]) for i in range(size)) or 1.0
        if min_diag > 0:
            condition_number = max_diag / min_diag
    if condition_number is not None and math.isfinite(condition_number):
        diagnostics["condition_number"] = round(condition_number, 2)

    vif_values: list[float] = []
    raw_factors = factors
    for target_index in range(len(raw_factors)):
        target = raw_factors[target_index]
        others = [
            raw_factors[index]
            for index in range(len(raw_factors))
            if index != target_index
        ]
        if not others:
            continue
        _, helper_r2, _, _ = _matrix_ols(target, others, min_observations=5)
        if helper_r2 is not None and helper_r2 < 1.0:
            vif_values.append(1.0 / max(1.0 - helper_r2, 1e-6))
    if vif_values:
        diagnostics["vif_max"] = round(max(vif_values), 2)

    residuals = [actual - predicted for actual, predicted in zip(y, fitted, strict=False)]
    from app.services.risk.regression_diagnostics import build_regression_diagnostics

    diagnostics.update(
        build_regression_diagnostics(
            coefficients=coefficients,
            design=design,
            residuals=residuals,
            r_squared=r_squared,
            observation_count=length,
            vif_max=diagnostics.get("vif_max"),
            condition_number=diagnostics.get("condition_number"),
        )
    )
    diagnostics["model_label"] = "ETF-proxy exposure model"

    return coefficients, r_squared, residual_std, diagnostics


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
    [series["SPY"][day] for day in common_dates]
    factor_names = ["Market", *FACTOR_PROXIES.keys()]
    factor_matrix = [[series["SPY"][day] for day in common_dates]]
    for name in FACTOR_PROXIES:
        proxy = FACTOR_PROXIES[name]
        factor_matrix.append(
            [series[proxy][day] - series["SPY"][day] for day in common_dates]
        )

    coefficients, r_squared, residual_std, diagnostics = _matrix_ols(aligned_portfolio, factor_matrix)
    if not coefficients:
        return {}, "regression_failed", {}

    exposures = {
        name: round(coefficients[index + 1], 4)
        for index, name in enumerate(factor_names)
        if math.isfinite(coefficients[index + 1])
    }
    if not exposures:
        return {}, "regression_failed", {}

    metadata: dict[str, Any] = {
        "observation_count": len(common_dates),
        "r_squared": round(r_squared, 4) if r_squared is not None else None,
        "residual_volatility": round(residual_std, 6) if residual_std is not None else None,
        "history_end": history_end.isoformat(),
        "diagnostics": diagnostics,
    }
    return exposures, "experimental", metadata
