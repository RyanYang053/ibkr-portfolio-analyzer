from __future__ import annotations

from typing import Any

import numpy as np
from scipy.cluster.hierarchy import leaves_list, linkage
from scipy.spatial.distance import squareform


def _correlation_matrix(covariance: np.ndarray) -> np.ndarray:
    diag = np.sqrt(np.clip(np.diag(covariance), 1e-12, None))
    outer = np.outer(diag, diag)
    return covariance / np.clip(outer, 1e-12, None)


def _inverse_variance_portfolio(covariance: np.ndarray) -> np.ndarray:
    diag = np.clip(np.diag(covariance), 1e-12, None)
    weights = 1.0 / diag
    total = float(weights.sum())
    if total <= 0:
        return np.ones(covariance.shape[0]) / max(covariance.shape[0], 1)
    return weights / total


def _cluster_variance(covariance: np.ndarray, indices: list[int]) -> float:
    if not indices:
        return 0.0
    sub = covariance[np.ix_(indices, indices)]
    weights = _inverse_variance_portfolio(sub).reshape(-1, 1)
    return float((weights.T @ sub @ weights).item())


def hierarchical_risk_parity_weights(covariance: list[list[float]]) -> list[float] | None:
    matrix = np.array(covariance, dtype=float)
    size = matrix.shape[0]
    if size == 0:
        return None
    if size == 1:
        return [1.0]

    correlation = _correlation_matrix(matrix)
    distance = np.sqrt(np.clip(0.5 * (1.0 - correlation), 0.0, None))
    np.fill_diagonal(distance, 0.0)
    condensed = squareform(distance, checks=False)
    link_matrix = linkage(condensed, method="single")
    sorted_indices = leaves_list(link_matrix).tolist()

    weights = np.ones(size, dtype=float)
    clusters: list[list[int]] = [sorted_indices]
    while clusters:
        next_clusters: list[list[int]] = []
        for cluster in clusters:
            if len(cluster) <= 1:
                continue
            midpoint = len(cluster) // 2
            left = cluster[:midpoint]
            right = cluster[midpoint:]
            left_var = _cluster_variance(matrix, left)
            right_var = _cluster_variance(matrix, right)
            if left_var + right_var <= 0:
                alpha = 0.5
            else:
                alpha = 1.0 - left_var / (left_var + right_var)
            for index in left:
                weights[index] *= alpha
            for index in right:
                weights[index] *= 1.0 - alpha
            if len(left) > 1:
                next_clusters.append(left)
            if len(right) > 1:
                next_clusters.append(right)
        clusters = next_clusters

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


def verify_weight_constraints(
    weights: list[float],
    *,
    sleeve_budget: float,
    current_weights: list[float] | None = None,
    turnover_budget: float | None = None,
    liquidity_caps: list[float] | None = None,
    max_weight: float | None = None,
    sector_labels: list[str] | None = None,
    sector_cap: float | None = None,
    fixed_sector_exposure: dict[str, float] | None = None,
    sleeve_portfolio_fraction: float = 1.0,
    tolerance: float = 1e-4,
) -> dict[str, Any]:
    violations: list[str] = []
    slack: dict[str, float] = {}
    total = sum(weights)
    slack["budget"] = round(sleeve_budget - total, 6)
    if abs(slack["budget"]) > tolerance:
        violations.append("budget")
    if current_weights is not None and turnover_budget is not None:
        turnover = sum(abs(left - right) for left, right in zip(weights, current_weights))
        slack["turnover"] = round(turnover_budget - turnover, 6)
        if turnover > turnover_budget + tolerance:
            violations.append("turnover")
    if liquidity_caps is not None:
        for index, cap in enumerate(liquidity_caps):
            slack[f"liquidity_{index}"] = round(cap - weights[index], 6)
            if weights[index] > cap + tolerance:
                violations.append(f"liquidity_{index}")
    if max_weight is not None:
        for index, weight in enumerate(weights):
            if weight > max_weight + tolerance:
                violations.append(f"max_weight_{index}")
    if sector_labels and sector_cap is not None:
        fixed_sector_exposure = fixed_sector_exposure or {}
        sector_totals: dict[str, float] = {}
        for index, label in enumerate(sector_labels):
            sector_totals[label] = sector_totals.get(label, 0.0) + weights[index]
        for sector, optimized in sector_totals.items():
            combined = optimized * sleeve_portfolio_fraction + fixed_sector_exposure.get(sector, 0.0)
            slack[f"sector_{sector}"] = round(sector_cap - combined, 6)
            if combined > sector_cap + tolerance:
                violations.append(f"sector_{sector}")
    return {"feasible": not violations, "violations": violations, "slack": slack}


def _apply_sector_constraints(
    constraints: list,
    weights,
    *,
    sector_labels: list[str] | None,
    sector_cap: float | None,
    fixed_sector_exposure: dict[str, float] | None,
    sleeve_portfolio_fraction: float = 1.0,
) -> None:
    if not sector_labels or sector_cap is None:
        return
    import cvxpy as cp

    fixed_sector_exposure = fixed_sector_exposure or {}
    sectors = sorted(set(sector_labels))
    for sector in sectors:
        indices = [index for index, label in enumerate(sector_labels) if label == sector]
        optimized = cp.sum(weights[indices])
        constraints.append(fixed_sector_exposure.get(sector, 0.0) + sleeve_portfolio_fraction * optimized <= sector_cap)


def solve_cvar_weights(
    returns_by_symbol: dict[str, list[float]],
    symbols: list[str],
    *,
    alpha: float = 0.95,
    sleeve_budget: float = 1.0,
    current_weights: list[float] | None = None,
    turnover_budget: float | None = None,
    liquidity_caps: list[float] | None = None,
    sector_labels: list[str] | None = None,
    sector_cap: float | None = None,
    fixed_sector_exposure: dict[str, float] | None = None,
    sleeve_portfolio_fraction: float = 1.0,
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
    tail_losses = cp.Variable(scenarios, nonneg=True)
    losses = -portfolio_returns
    constraints = [
        cp.sum(weights) == sleeve_budget,
        tail_losses >= losses - var,
    ]
    if current_weights is not None and turnover_budget is not None:
        current = np.array(current_weights, dtype=float)
        constraints.append(cp.norm1(weights - current) <= turnover_budget)
    if liquidity_caps is not None:
        for index, cap in enumerate(liquidity_caps):
            constraints.append(weights[index] <= cap)
    _apply_sector_constraints(
        constraints,
        weights,
        sector_labels=sector_labels,
        sector_cap=sector_cap,
        fixed_sector_exposure=fixed_sector_exposure,
        sleeve_portfolio_fraction=sleeve_portfolio_fraction,
    )

    problem = cp.Problem(
        cp.Minimize(var + (1.0 / ((1.0 - alpha) * scenarios)) * cp.sum(tail_losses)),
        constraints,
    )
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
    feasibility = verify_weight_constraints(
        normalized,
        sleeve_budget=sleeve_budget,
        current_weights=current_weights,
        turnover_budget=turnover_budget,
        liquidity_caps=liquidity_caps,
        sector_labels=sector_labels,
        sector_cap=sector_cap,
        fixed_sector_exposure=fixed_sector_exposure,
        sleeve_portfolio_fraction=sleeve_portfolio_fraction,
    )
    return normalized, {
        "status": problem.status,
        "objective": float(problem.value) if problem.value is not None else None,
        "feasibility": feasibility,
    }


def solve_mean_variance_with_constraints(
    covariance: list[list[float]],
    expected_returns: list[float],
    *,
    sleeve_budget: float = 1.0,
    current_weights: list[float] | None = None,
    turnover_budget: float | None = None,
    liquidity_caps: list[float] | None = None,
    max_weight: float | None = None,
    sector_labels: list[str] | None = None,
    sector_cap: float | None = None,
    fixed_sector_exposure: dict[str, float] | None = None,
    sleeve_portfolio_fraction: float = 1.0,
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
    _apply_sector_constraints(
        constraints,
        weights,
        sector_labels=sector_labels,
        sector_cap=sector_cap,
        fixed_sector_exposure=fixed_sector_exposure,
        sleeve_portfolio_fraction=sleeve_portfolio_fraction,
    )
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
    normalized = [value / total * sleeve_budget for value in values]
    feasibility = verify_weight_constraints(
        normalized,
        sleeve_budget=sleeve_budget,
        current_weights=current_weights,
        turnover_budget=turnover_budget,
        liquidity_caps=liquidity_caps,
        max_weight=max_weight,
        sector_labels=sector_labels,
        sector_cap=sector_cap,
        fixed_sector_exposure=fixed_sector_exposure,
        sleeve_portfolio_fraction=sleeve_portfolio_fraction,
    )
    return normalized, {"status": problem.status, "feasibility": feasibility}
