from __future__ import annotations

import numpy as np
import pytest

from app.services.portfolio_construction.advanced_optimizer import (
    OptimizationConstraints,
    build_cvxpy_constraints,
    solve_min_variance_with_constraints,
    verify_optimization_constraints,
)


def _base_constraints(**overrides) -> OptimizationConstraints:
    payload = dict(
        target_budget=0.7,
        current_full_weights=np.array([0.35, 0.35]),
        turnover_budget=0.5,
        max_buy_weight_changes=None,
        max_sell_weight_changes=None,
        max_weights=np.array([0.6, 0.6]),
        minimum_weights=None,
        sector_labels=["Tech", "Tech"],
        sector_cap=0.8,
        fixed_sector_exposure={"Financials": 0.05},
    )
    payload.update(overrides)
    return OptimizationConstraints(**payload)


def test_build_cvxpy_constraints_includes_budget_turnover_and_sector_caps():
    import cvxpy as cp

    weights = cp.Variable(2, nonneg=True)
    constraints = build_cvxpy_constraints(weights, _base_constraints())
    assert len(constraints) >= 5


def test_min_variance_respects_single_name_and_liquidity_caps():
    covariance = [[0.04, 0.01], [0.01, 0.09]]
    constraints = _base_constraints(max_weights=np.array([0.35, 0.35]), target_budget=0.7)
    weights, metadata = solve_min_variance_with_constraints(covariance, constraints)
    if metadata.get("status") == "cvxpy_unavailable":
        pytest.skip("cvxpy unavailable")
    assert weights is not None
    assert metadata["feasibility"]["feasible"] is True
    assert all(weight <= 0.35 + 1e-4 for weight in weights)
    assert pytest.approx(sum(weights), rel=1e-4) == 0.7


def test_tight_turnover_budget_can_make_problem_infeasible():
    covariance = [[0.04, 0.0], [0.0, 0.09]]
    constraints = _base_constraints(
        target_budget=0.3,
        current_full_weights=np.array([0.2, 0.8]),
        turnover_budget=0.05,
        max_buy_weight_changes=None,
        max_sell_weight_changes=None,
        max_weights=np.array([0.15, 0.15]),
        sector_cap=0.3,
        fixed_sector_exposure={},
    )
    weights, metadata = solve_min_variance_with_constraints(covariance, constraints)
    if metadata.get("status") == "cvxpy_unavailable":
        pytest.skip("cvxpy unavailable")
    assert weights is None or metadata.get("status", "").startswith("infeasible")


def test_fixed_sector_exposure_reduces_remaining_capacity():
    constraints = _base_constraints(
        sector_labels=["Tech", "Financials"],
        sector_cap=0.65,
        fixed_sector_exposure={"Tech": 0.2},
        max_weights=np.array([1.0, 1.0]),
        max_buy_weight_changes=None,
        max_sell_weight_changes=None,
        turnover_budget=1.0,
        target_budget=0.5,
    )
    feasible = verify_optimization_constraints([0.25, 0.25], constraints)
    assert feasible["feasible"] is True
    result = verify_optimization_constraints([0.50, 0.0], constraints)
    assert result["feasible"] is False
