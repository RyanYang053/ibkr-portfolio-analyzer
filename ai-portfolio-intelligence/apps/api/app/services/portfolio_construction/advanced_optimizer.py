from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.cluster.hierarchy import leaves_list, linkage
from scipy.spatial.distance import squareform

InstrumentKey = tuple[int | None, str, str, str]


@dataclass(frozen=True)
class OptimizationConstraints:
    target_budget: float
    current_full_weights: np.ndarray
    turnover_budget: float | None
    max_buy_weight_changes: np.ndarray | None
    max_sell_weight_changes: np.ndarray | None
    max_weights: np.ndarray | None
    minimum_weights: np.ndarray | None
    sector_labels: list[str]
    sector_cap: float | None
    fixed_sector_exposure: dict[str, float]
    tax_budget: float | None = None
    transaction_cost_budget: float | None = None
    sell_tax_rate_per_unit: np.ndarray | None = None
    transaction_cost_rate_per_unit: np.ndarray | None = None


def build_cvxpy_constraints(weights, constraints: OptimizationConstraints) -> list:
    import cvxpy as cp

    built: list = [
        cp.sum(weights) == constraints.target_budget,
        weights >= 0,
    ]
    if constraints.minimum_weights is not None:
        built.append(weights >= constraints.minimum_weights)
    if constraints.turnover_budget is not None:
        built.append(cp.norm1(weights - constraints.current_full_weights) <= constraints.turnover_budget)
    weight_change = weights - constraints.current_full_weights
    if constraints.max_buy_weight_changes is not None:
        built.append(weight_change <= constraints.max_buy_weight_changes)
    if constraints.max_sell_weight_changes is not None:
        built.append(-weight_change <= constraints.max_sell_weight_changes)
    if constraints.max_weights is not None:
        built.append(weights <= constraints.max_weights)
    if constraints.sector_labels and constraints.sector_cap is not None:
        sectors = sorted(set(constraints.sector_labels))
        for sector in sectors:
            indices = [index for index, label in enumerate(constraints.sector_labels) if label == sector]
            optimized = cp.sum(weights[indices])
            fixed = constraints.fixed_sector_exposure.get(sector, 0.0)
            built.append(fixed + optimized <= constraints.sector_cap)
    if (
        constraints.tax_budget is not None
        and constraints.sell_tax_rate_per_unit is not None
    ) or (
        constraints.transaction_cost_budget is not None
        and constraints.transaction_cost_rate_per_unit is not None
    ):
        size = len(constraints.current_full_weights)
        buy = cp.Variable(size, nonneg=True)
        sell = cp.Variable(size, nonneg=True)
        built.append(weights - constraints.current_full_weights == buy - sell)
        if constraints.tax_budget is not None and constraints.sell_tax_rate_per_unit is not None:
            built.append(constraints.sell_tax_rate_per_unit @ sell <= constraints.tax_budget)
        if constraints.transaction_cost_budget is not None and constraints.transaction_cost_rate_per_unit is not None:
            built.append(
                constraints.transaction_cost_rate_per_unit @ (buy + sell)
                <= constraints.transaction_cost_budget
            )
    return built


def verify_optimization_constraints(
    weights: list[float],
    constraints: OptimizationConstraints,
    *,
    tolerance: float = 1e-4,
) -> dict[str, Any]:
    result = verify_weight_constraints(
        weights,
        target_budget=constraints.target_budget,
        current_full_weights=[float(value) for value in constraints.current_full_weights],
        turnover_budget=constraints.turnover_budget,
        liquidity_caps=None,
        max_weight=None,
        minimum_weights=(
            [float(value) for value in constraints.minimum_weights]
            if constraints.minimum_weights is not None
            else None
        ),
        sector_labels=constraints.sector_labels,
        sector_cap=constraints.sector_cap,
        fixed_sector_exposure=constraints.fixed_sector_exposure,
        tolerance=tolerance,
    )
    if constraints.max_weights is not None:
        for index, weight in enumerate(weights):
            cap = float(constraints.max_weights[index])
            slack_key = f"max_weight_{index}"
            result["slack"][slack_key] = round(cap - weight, 6)
            if weight > cap + tolerance:
                result["violations"].append(slack_key)
    current = constraints.current_full_weights
    target = np.asarray(weights, dtype=float)
    changes = target - current

    if constraints.max_buy_weight_changes is not None:
        for index, change in enumerate(changes):
            limit = float(constraints.max_buy_weight_changes[index])
            slack_key = f"liquidity_buy_{index}"
            result["slack"][slack_key] = round(limit - max(float(change), 0.0), 6)
            if float(change) > limit + tolerance:
                result["violations"].append(slack_key)

    if constraints.max_sell_weight_changes is not None:
        for index, change in enumerate(changes):
            limit = float(constraints.max_sell_weight_changes[index])
            sell_change = max(-float(change), 0.0)
            slack_key = f"liquidity_sell_{index}"
            result["slack"][slack_key] = round(limit - sell_change, 6)
            if sell_change > limit + tolerance:
                result["violations"].append(slack_key)

    result["feasible"] = not result["violations"]
    return result


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
    target_budget: float,
    current_full_weights: list[float] | None = None,
    turnover_budget: float | None = None,
    liquidity_caps: list[float] | None = None,
    max_weight: float | None = None,
    minimum_weights: list[float] | None = None,
    sector_labels: list[str] | None = None,
    sector_cap: float | None = None,
    fixed_sector_exposure: dict[str, float] | None = None,
    tolerance: float = 1e-4,
) -> dict[str, Any]:
    violations: list[str] = []
    slack: dict[str, float] = {}
    total = sum(weights)
    slack["budget"] = round(target_budget - total, 6)
    if abs(slack["budget"]) > tolerance:
        violations.append("budget")
    if current_full_weights is not None and turnover_budget is not None:
        turnover = sum(abs(left - right) for left, right in zip(weights, current_full_weights, strict=False))
        slack["turnover"] = round(turnover_budget - turnover, 6)
        if turnover > turnover_budget + tolerance:
            violations.append("turnover")
    if minimum_weights is not None:
        for index, minimum in enumerate(minimum_weights):
            if weights[index] + tolerance < minimum:
                violations.append(f"minimum_weight_{index}")
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
            combined = optimized + fixed_sector_exposure.get(sector, 0.0)
            slack[f"sector_{sector}"] = round(sector_cap - combined, 6)
            if combined > sector_cap + tolerance:
                violations.append(f"sector_{sector}")
    return {"feasible": not violations, "violations": violations, "slack": slack}


def _finalize_solver_weights(
    weights: np.ndarray,
    constraints: OptimizationConstraints,
) -> tuple[list[float] | None, dict[str, Any]]:
    values = [max(0.0, float(value)) for value in weights]
    feasibility = verify_optimization_constraints(values, constraints)
    if not feasibility["feasible"]:
        return None, {"status": "post_solve_infeasible", "feasibility": feasibility}
    return values, {"feasibility": feasibility}


def solve_min_variance_with_constraints(
    covariance: list[list[float]],
    constraints: OptimizationConstraints,
) -> tuple[list[float] | None, dict[str, Any]]:
    try:
        import cvxpy as cp
    except ImportError:
        return None, {"status": "cvxpy_unavailable"}

    size = len(covariance)
    if size == 0:
        return None, {"status": "empty_covariance"}
    sigma = np.array(covariance, dtype=float)
    weights = cp.Variable(size, nonneg=True)
    problem = cp.Problem(
        cp.Minimize(cp.quad_form(weights, sigma)),
        build_cvxpy_constraints(weights, constraints),
    )
    try:
        problem.solve(solver=cp.OSQP, warm_start=True)
    except Exception:
        problem.solve()
    if weights.value is None or problem.status not in {"optimal", "optimal_inaccurate"}:
        return None, {"status": problem.status or "solver_failed"}
    finalized, metadata = _finalize_solver_weights(weights.value, constraints)
    if finalized is None:
        return None, metadata
    return finalized, {"status": problem.status, **metadata}


def solve_cvar_weights(
    returns_by_symbol: dict[str, list[float]],
    symbols: list[str],
    *,
    alpha: float = 0.95,
    target_budget: float = 1.0,
    current_full_weights: list[float] | None = None,
    turnover_budget: float | None = None,
    max_buy_weight_changes: list[float] | None = None,
    max_sell_weight_changes: list[float] | None = None,
    max_weights: np.ndarray | None = None,
    minimum_weights: np.ndarray | None = None,
    sector_labels: list[str] | None = None,
    sector_cap: float | None = None,
    fixed_sector_exposure: dict[str, float] | None = None,
    tax_budget: float | None = None,
    transaction_cost_budget: float | None = None,
    sell_tax_rate_per_unit: np.ndarray | None = None,
    transaction_cost_rate_per_unit: np.ndarray | None = None,
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
    constraint_set = OptimizationConstraints(
        target_budget=target_budget,
        current_full_weights=np.array(current_full_weights if current_full_weights is not None else [0.0] * assets),
        turnover_budget=turnover_budget,
        max_buy_weight_changes=(
            np.array(max_buy_weight_changes, dtype=float) if max_buy_weight_changes is not None else None
        ),
        max_sell_weight_changes=(
            np.array(max_sell_weight_changes, dtype=float) if max_sell_weight_changes is not None else None
        ),
        max_weights=max_weights,
        minimum_weights=minimum_weights,
        sector_labels=sector_labels or [],
        sector_cap=sector_cap,
        fixed_sector_exposure=fixed_sector_exposure or {},
        tax_budget=tax_budget,
        transaction_cost_budget=transaction_cost_budget,
        sell_tax_rate_per_unit=sell_tax_rate_per_unit,
        transaction_cost_rate_per_unit=transaction_cost_rate_per_unit,
    )
    constraints = build_cvxpy_constraints(weights, constraint_set)
    constraints.extend([tail_losses >= losses - var])

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
    finalized, metadata = _finalize_solver_weights(weights.value, constraint_set)
    if finalized is None:
        return None, metadata
    return finalized, {
        "status": problem.status,
        "objective": float(problem.value) if problem.value is not None else None,
        **metadata,
    }


def solve_mean_variance_with_constraints(
    covariance: list[list[float]],
    expected_returns: list[float],
    *,
    target_budget: float = 1.0,
    current_full_weights: list[float] | None = None,
    turnover_budget: float | None = None,
    max_buy_weight_changes: list[float] | None = None,
    max_sell_weight_changes: list[float] | None = None,
    max_weight: float | None = None,
    max_weights: np.ndarray | None = None,
    minimum_weights: np.ndarray | None = None,
    sector_labels: list[str] | None = None,
    sector_cap: float | None = None,
    fixed_sector_exposure: dict[str, float] | None = None,
    tax_budget: float | None = None,
    transaction_cost_budget: float | None = None,
    sell_tax_rate_per_unit: np.ndarray | None = None,
    transaction_cost_rate_per_unit: np.ndarray | None = None,
) -> tuple[list[float] | None, dict[str, Any]]:
    try:
        import cvxpy as cp
    except ImportError:
        return None, {"status": "cvxpy_unavailable"}

    size = len(covariance)
    sigma = np.array(covariance, dtype=float)
    mu = np.array(expected_returns, dtype=float)
    weights = cp.Variable(size, nonneg=True)
    resolved_max_weights = max_weights
    if resolved_max_weights is None and max_weight is not None:
        resolved_max_weights = np.full(size, max_weight)
    constraint_set = OptimizationConstraints(
        target_budget=target_budget,
        current_full_weights=np.array(current_full_weights if current_full_weights is not None else [0.0] * size),
        turnover_budget=turnover_budget,
        max_buy_weight_changes=(
            np.array(max_buy_weight_changes, dtype=float) if max_buy_weight_changes is not None else None
        ),
        max_sell_weight_changes=(
            np.array(max_sell_weight_changes, dtype=float) if max_sell_weight_changes is not None else None
        ),
        max_weights=resolved_max_weights,
        minimum_weights=minimum_weights,
        sector_labels=sector_labels or [],
        sector_cap=sector_cap,
        fixed_sector_exposure=fixed_sector_exposure or {},
        tax_budget=tax_budget,
        transaction_cost_budget=transaction_cost_budget,
        sell_tax_rate_per_unit=sell_tax_rate_per_unit,
        transaction_cost_rate_per_unit=transaction_cost_rate_per_unit,
    )
    constraints = build_cvxpy_constraints(weights, constraint_set)
    problem = cp.Problem(cp.Maximize(mu @ weights - 0.5 * cp.quad_form(weights, sigma)), constraints)
    try:
        problem.solve(solver=cp.OSQP, warm_start=True)
    except Exception:
        problem.solve()
    if weights.value is None or problem.status not in {"optimal", "optimal_inaccurate"}:
        return None, {"status": problem.status or "solver_failed"}
    finalized, metadata = _finalize_solver_weights(weights.value, constraint_set)
    if finalized is None:
        return None, metadata
    return finalized, {"status": problem.status, **metadata}
