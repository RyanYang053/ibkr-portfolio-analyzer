from __future__ import annotations

import numpy as np
import pytest

from app.services.portfolio_construction.advanced_optimizer import (
    OptimizationConstraints,
    solve_min_variance_with_constraints,
)


def test_infeasible_problem_returns_explicit_status():
    covariance = [[0.04, 0.0], [0.0, 0.09]]
    constraints = OptimizationConstraints(
        target_budget=0.8,
        current_full_weights=np.array([0.1, 0.7]),
        turnover_budget=0.01,
        liquidity_caps=np.array([0.2, 0.2]),
        max_weights=np.array([0.2, 0.2]),
        minimum_weights=None,
        sector_labels=["Tech", "Tech"],
        sector_cap=0.25,
        fixed_sector_exposure={},
    )
    weights, metadata = solve_min_variance_with_constraints(covariance, constraints)
    if metadata.get("status") == "cvxpy_unavailable":
        pytest.skip("cvxpy unavailable")
    assert weights is None or metadata.get("status") in {"infeasible", "infeasible_inaccurate", "solver_failed", "post_solve_infeasible"}
