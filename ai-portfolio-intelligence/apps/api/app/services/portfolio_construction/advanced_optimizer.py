from __future__ import annotations

import math
from statistics import fmean
from typing import Any

import numpy as np


def _correlation_matrix(covariance: np.ndarray) -> np.ndarray:
    diag = np.sqrt(np.clip(np.diag(covariance), 1e-12, None))
    outer = np.outer(diag, diag)
    return covariance / np.clip(outer, 1e-12, None)


def hierarchical_risk_parity_weights(covariance: list[list[float]]) -> list[float] | None:
    matrix = np.array(covariance, dtype=float)
    size = matrix.shape[0]
    if size == 0:
        return None
    correlation = _correlation_matrix(matrix)
    distance = np.sqrt(0.5 * (1.0 - correlation))
    order = list(range(size))
    clusters = [order[:]]

    while len(clusters) > 1:
        minimum = math.inf
        merge = (0, 1)
        for left_index in range(len(clusters)):
            for right_index in range(left_index + 1, len(clusters)):
                left = clusters[left_index]
                right = clusters[right_index]
                distances = [distance[i, j] for i in left for j in right]
                average = fmean(distances)
                if average < minimum:
                    minimum = average
                    merge = (left_index, right_index)
        left_cluster = clusters.pop(merge[1])
        clusters[merge[0]].extend(left_cluster)

    weights = np.ones(size, dtype=float)
    for cluster in clusters:
        if len(cluster) <= 1:
            continue
        midpoint = len(cluster) // 2
        left = cluster[:midpoint]
        right = cluster[midpoint:]
        left_var = sum(matrix[i, i] for i in left)
        right_var = sum(matrix[i, i] for i in right)
        if left_var + right_var <= 0:
            continue
        right_scale = left_var / (left_var + right_var)
        left_scale = 1.0 - right_scale
        for index in left:
            weights[index] *= left_scale
        for index in right:
            weights[index] *= right_scale
    total = float(weights.sum())
    if total <= 0:
        return None
    return [float(value / total) for value in weights]


def black_litterman_posterior_returns(
    covariance: list[list[float]],
    market_weights: list[float],
    views: dict[int, float] | None = None,
    *,
    risk_aversion: float = 2.5,
    tau: float = 0.05,
    view_confidence: float = 0.5,
) -> list[float]:
    sigma = np.array(covariance, dtype=float)
    weights = np.array(market_weights, dtype=float)
    if weights.sum() <= 0:
        weights = np.ones(len(market_weights)) / len(market_weights)
    else:
        weights = weights / weights.sum()
    pi = risk_aversion * sigma @ weights
    if not views:
        return [float(value) for value in pi]
    assets = sorted(views)
    p = np.zeros((len(assets), len(market_weights)))
    q = np.zeros(len(assets))
    for row, asset in enumerate(assets):
        p[row, asset] = 1.0
        q[row] = views[asset]
    omega = np.eye(len(assets)) * ((1.0 - view_confidence) / max(view_confidence, 1e-6))
    tau_sigma = tau * sigma
    middle = np.linalg.inv(np.linalg.inv(tau_sigma) + p.T @ np.linalg.inv(omega) @ p)
    rhs = np.linalg.inv(tau_sigma) @ pi + p.T @ np.linalg.inv(omega) @ q
    posterior = middle @ rhs
    return [float(value) for value in posterior]


def solve_cvar_weights(
    returns_by_symbol: dict[str, list[float]],
    symbols: list[str],
    *,
    alpha: float = 0.95,
    sleeve_budget: float = 1.0,
    current_weights: list[float] | None = None,
    turnover_budget: float | None = None,
    liquidity_caps: list[float] | None = None,
) -> tuple[list[float] | None, dict[str, Any]]:
    try:
        import cvxpy as cp
    except ImportError:
        return None, {"status": "cvxpy_unavailable"}

    matrix = np.array([returns_by_symbol[symbol] for symbol in symbols], dtype=float).T
    scenarios, assets = matrix.shape
    if scenarios < 30 or assets == 0:
        return None, {"status": "insufficient_scenarios"}

    weights = cp.Variable(assets, nonneg=True)
    portfolio_returns = matrix @ weights
    var = cp.Variable()
    losses = -portfolio_returns
    tail = cp.Variable(scenarios, nonneg=True)
    constraints = [
        cp.sum(weights) == sleeve_budget,
        tail >= losses - var,
        cp.sum(tail) <= (1.0 - alpha) * scenarios,
    ]
    if current_weights is not None and turnover_budget is not None:
        current = np.array(current_weights, dtype=float)
        constraints.append(cp.norm1(weights - current) <= turnover_budget)
    if liquidity_caps is not None:
        for index, cap in enumerate(liquidity_caps):
            constraints.append(weights[index] <= cap)

    problem = cp.Problem(cp.Minimize(var + (1.0 / ((1.0 - alpha) * scenarios)) * cp.sum(tail)), constraints)
    try:
        problem.solve(solver=cp.OSQP, warm_start=True)
    except Exception:
        problem.solve()
    if weights.value is None or problem.status not in {"optimal", "optimal_inaccurate"}:
        return None, {"status": problem.status or "solver_failed"}
    values = [float(value) for value in weights.value]
    total = sum(values)
    if total <= 0:
        return None, {"status": "zero_weights"}
    normalized = [value / total * sleeve_budget for value in values]
    return normalized, {"status": problem.status, "objective": float(problem.value) if problem.value is not None else None}


def solve_mean_variance_with_constraints(
    covariance: list[list[float]],
    expected_returns: list[float],
    *,
    sleeve_budget: float = 1.0,
    current_weights: list[float] | None = None,
    turnover_budget: float | None = None,
    liquidity_caps: list[float] | None = None,
    max_weight: float | None = None,
) -> tuple[list[float] | None, dict[str, Any]]:
    try:
        import cvxpy as cp
    except ImportError:
        return None, {"status": "cvxpy_unavailable"}

    size = len(covariance)
    sigma = np.array(covariance, dtype=float)
    mu = np.array(expected_returns, dtype=float)
    weights = cp.Variable(size, nonneg=True)
    constraints = [cp.sum(weights) == sleeve_budget]
    if current_weights is not None and turnover_budget is not None:
        constraints.append(cp.norm1(weights - np.array(current_weights)) <= turnover_budget)
    if liquidity_caps is not None:
        for index, cap in enumerate(liquidity_caps):
            constraints.append(weights[index] <= cap)
    if max_weight is not None:
        constraints.append(weights <= max_weight)
    problem = cp.Problem(cp.Maximize(mu @ weights - 0.5 * cp.quad_form(weights, sigma)), constraints)
    try:
        problem.solve(solver=cp.OSQP, warm_start=True)
    except Exception:
        problem.solve()
    if weights.value is None or problem.status not in {"optimal", "optimal_inaccurate"}:
        return None, {"status": problem.status or "solver_failed"}
    values = [float(value) for value in weights.value]
    total = sum(values)
    if total <= 0:
        return None, {"status": "zero_weights"}
    return [value / total * sleeve_budget for value in values], {"status": problem.status}
