from __future__ import annotations

import math
from statistics import fmean
from typing import Any


TRADING_DAYS = 252


def newey_west_lag(observation_count: int) -> int:
    if observation_count <= 1:
        return 0
    return max(1, int(math.floor(4.0 * (observation_count / 100.0) ** (2.0 / 9.0))))


def newey_west_standard_errors(
    design: list[list[float]],
    residuals: list[float],
    *,
    lag: int | None = None,
) -> list[float] | None:
    length = len(residuals)
    if length <= len(design[0]) if design else 0:
        return None

    size = len(design[0])
    normal = [[0.0 for _ in range(size)] for _ in range(size)]
    for row_index, row in enumerate(design):
        for i in range(size):
            for j in range(size):
                normal[i][j] += row[i] * row[j]

    inverse = _invert_matrix(normal)
    if inverse is None:
        return None

    resolved_lag = newey_west_lag(length) if lag is None else lag
    meat = [[0.0 for _ in range(size)] for _ in range(size)]
    for row_index, row in enumerate(design):
        residual = residuals[row_index]
        for i in range(size):
            for j in range(size):
                meat[i][j] += (residual ** 2) * row[i] * row[j]

    for step in range(1, resolved_lag + 1):
        weight = 1.0 - step / (resolved_lag + 1.0)
        for row_index in range(step, length):
            left = design[row_index]
            right = design[row_index - step]
            residual_product = residuals[row_index] * residuals[row_index - step]
            for i in range(size):
                for j in range(size):
                    adjustment = weight * residual_product * (left[i] * right[j] + right[i] * left[j])
                    meat[i][j] += adjustment

    sandwich = [[0.0 for _ in range(size)] for _ in range(size)]
    for i in range(size):
        for j in range(size):
            for left in range(size):
                for right in range(size):
                    sandwich[i][j] += inverse[i][left] * meat[left][right] * inverse[right][j]

    return [math.sqrt(max(sandwich[index][index], 0.0)) for index in range(size)]


def _invert_matrix(matrix: list[list[float]]) -> list[list[float]] | None:
    size = len(matrix)
    augmented = [matrix[row][:] + [1.0 if index == row else 0.0 for index in range(size)] for row in range(size)]
    for pivot in range(size):
        diag = augmented[pivot][pivot]
        if abs(diag) < 1e-12:
            return None
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
    return [row[size:] for row in augmented]


def build_regression_diagnostics(
    *,
    coefficients: list[float],
    design: list[list[float]],
    residuals: list[float],
    r_squared: float | None,
    observation_count: int,
    vif_max: float | None,
    condition_number: float | None,
) -> dict[str, Any]:
    hac_standard_errors = newey_west_standard_errors(design, residuals)
    coefficient_rows: list[dict[str, Any]] = []
    for index, coefficient in enumerate(coefficients):
        hac_se = hac_standard_errors[index] if hac_standard_errors else None
        t_stat = coefficient / hac_se if hac_se and hac_se > 0 else None
        confidence_interval = None
        if hac_se and hac_se > 0:
            confidence_interval = [round(coefficient - 1.96 * hac_se, 6), round(coefficient + 1.96 * hac_se, 6)]
        coefficient_rows.append(
            {
                "coefficient": round(coefficient, 6),
                "hac_standard_error": round(hac_se, 6) if hac_se and hac_se > 0 else None,
                "t_statistic": round(t_stat, 4) if t_stat is not None and math.isfinite(t_stat) else None,
                "confidence_interval_95": confidence_interval,
            }
        )

    adjusted_r_squared = None
    if r_squared is not None and observation_count > len(coefficients) + 1:
        adjusted_r_squared = 1.0 - (1.0 - r_squared) * (observation_count - 1) / max(
            observation_count - len(coefficients) - 1,
            1,
        )

    return {
        "model_label": "ETF-proxy exposure model (HAC inference)",
        "observation_count": observation_count,
        "r_squared": round(r_squared, 4) if r_squared is not None else None,
        "adjusted_r_squared": round(adjusted_r_squared, 4) if adjusted_r_squared is not None else None,
        "condition_number": round(condition_number, 2) if condition_number is not None else None,
        "vif_max": round(vif_max, 2) if vif_max is not None else None,
        "newey_west_lag": newey_west_lag(observation_count),
        "coefficients": coefficient_rows,
        "residual_mean": round(fmean(residuals), 6) if residuals else None,
    }
