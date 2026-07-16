from __future__ import annotations

import numpy as np

from app.services.portfolio_construction.advanced_optimizer import (
    OptimizationConstraints,
    verify_optimization_constraints,
)


def test_no_trade_baseline_satisfies_zero_turnover():
    current = np.array([0.25, 0.20, 0.15])
    constraints = OptimizationConstraints(
        target_budget=float(current.sum()),
        current_full_weights=current,
        turnover_budget=0.0,
        max_buy_weight_changes=None,
        max_sell_weight_changes=None,
        max_weights=np.array([0.5, 0.5, 0.5]),
        minimum_weights=None,
        sector_labels=["Tech", "Tech", "Energy"],
        sector_cap=0.8,
        fixed_sector_exposure={},
    )
    result = verify_optimization_constraints([0.25, 0.20, 0.15], constraints)
    assert result["feasible"] is True
    assert result["slack"]["turnover"] == 0.0
