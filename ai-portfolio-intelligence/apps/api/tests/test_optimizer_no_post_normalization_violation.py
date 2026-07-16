from __future__ import annotations

import numpy as np
import pytest

from app.services.portfolio_construction.advanced_optimizer import (
    OptimizationConstraints,
    solve_min_variance_with_constraints,
)


def test_solver_does_not_post_normalize_away_from_target_budget():
    covariance = [[0.04, 0.01], [0.01, 0.09]]
    constraints = OptimizationConstraints(
        target_budget=0.55,
        current_full_weights=np.array([0.30, 0.25]),
        turnover_budget=0.20,
        max_buy_weight_changes=None,
        max_sell_weight_changes=None,
        max_weights=np.array([0.40, 0.40]),
        minimum_weights=None,
        sector_labels=["Tech", "Tech"],
        sector_cap=0.60,
        fixed_sector_exposure={},
    )
    weights, metadata = solve_min_variance_with_constraints(covariance, constraints)
    if metadata.get("status") == "cvxpy_unavailable":
        pytest.skip("cvxpy unavailable")
    assert weights is not None
    assert metadata.get("status") != "post_solve_infeasible"
    assert pytest.approx(sum(weights), rel=1e-3) == 0.55
