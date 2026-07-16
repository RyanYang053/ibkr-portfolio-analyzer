from __future__ import annotations

import pytest

from app.services.portfolio_construction.advanced_optimizer import (
    hierarchical_risk_parity_weights,
    solve_cvar_weights,
)


def test_hrp_reference_solution_sums_to_one():
    covariance = [
        [0.04, 0.01, 0.005],
        [0.01, 0.09, 0.02],
        [0.005, 0.02, 0.16],
    ]
    weights = hierarchical_risk_parity_weights(covariance)
    assert weights is not None
    assert pytest.approx(sum(weights), rel=1e-6) == 1.0
    assert all(weight >= 0 for weight in weights)


def test_cvar_small_problem_matches_known_feasible_region():
    returns_by_symbol = {
        "AAA": [0.01, -0.02, 0.015, -0.01, 0.005] * 8,
        "BBB": [-0.005, 0.02, -0.01, 0.01, 0.0] * 8,
    }
    weights, metadata = solve_cvar_weights(
        returns_by_symbol,
        ["AAA", "BBB"],
        target_budget=1.0,
        current_full_weights=[0.5, 0.5],
        turnover_budget=1.0,
        max_buy_weight_changes=None,
        max_sell_weight_changes=None,
    )
    if metadata.get("status") == "cvxpy_unavailable":
        pytest.skip("cvxpy unavailable")
    assert weights is not None
    assert pytest.approx(sum(weights), rel=1e-4) == 1.0
    assert metadata["feasibility"]["feasible"] is True
