from __future__ import annotations

from app.services.portfolio_construction.advanced_optimizer import OptimizationConstraints, verify_optimization_constraints
import numpy as np


def test_sleeve_relative_cap_accounts_for_fixed_sector_exposure():
    constraints = OptimizationConstraints(
        sleeve_budget=1.0,
        current_weights=np.array([0.5, 0.5]),
        turnover_budget=1.0,
        liquidity_caps=np.array([1.0, 1.0]),
        max_weights=np.array([1.0, 1.0]),
        sector_labels=["Tech", "Financials"],
        sector_cap=0.65,
        fixed_sector_exposure={"Tech": 0.2},
        sleeve_portfolio_fraction=0.5,
    )
    # 0.2 fixed Tech + 0.5 * 0.5 Tech sleeve weight = 0.45
    within_cap = verify_optimization_constraints([0.5, 0.5], constraints)
    assert within_cap["feasible"] is True
    # 0.2 fixed Tech + 0.5 * 0.95 Tech sleeve weight = 0.675
    overweight = verify_optimization_constraints([0.95, 0.05], constraints)
    assert overweight["feasible"] is False
    assert "sector_Tech" in overweight["violations"]
