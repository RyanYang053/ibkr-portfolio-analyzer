from __future__ import annotations

import numpy as np

from app.services.portfolio_construction.advanced_optimizer import (
    OptimizationConstraints,
    verify_optimization_constraints,
)


def test_full_portfolio_sector_cap_accounts_for_fixed_exposure():
    constraints = OptimizationConstraints(
        target_budget=0.5,
        current_full_weights=np.array([0.25, 0.25]),
        turnover_budget=1.0,
        max_buy_weight_changes=None,
        max_sell_weight_changes=None,
        max_weights=np.array([0.5, 0.5]),
        minimum_weights=None,
        sector_labels=["Tech", "Financials"],
        sector_cap=0.65,
        fixed_sector_exposure={"Tech": 0.2},
    )
    within_cap = verify_optimization_constraints([0.25, 0.25], constraints)
    assert within_cap["feasible"] is True
    overweight = verify_optimization_constraints([0.50, 0.0], constraints)
    assert overweight["feasible"] is False
    assert "sector_Tech" in overweight["violations"]
