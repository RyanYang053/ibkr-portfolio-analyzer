from __future__ import annotations

import numpy as np
import pytest

from app.services.portfolio_construction.advanced_optimizer import OptimizationConstraints, verify_optimization_constraints


def test_full_portfolio_turnover_uses_absolute_current_weights():
    constraints = OptimizationConstraints(
        target_budget=0.6,
        current_full_weights=np.array([0.2, 0.1]),
        turnover_budget=0.35,
        liquidity_caps=np.array([0.4, 0.4]),
        max_weights=np.array([0.4, 0.4]),
        minimum_weights=None,
        sector_labels=["Tech", "Financials"],
        sector_cap=0.5,
        fixed_sector_exposure={"Energy": 0.1},
    )
    feasible = verify_optimization_constraints([0.22, 0.38], constraints)
    assert feasible["feasible"] is True
    assert feasible["slack"]["budget"] == round(0.6 - 0.6, 6)
    turnover = sum(abs(a - b) for a, b in zip([0.22, 0.38], [0.2, 0.1]))
    assert turnover == pytest.approx(0.3)
    infeasible = verify_optimization_constraints([0.35, 0.35], constraints)
    assert infeasible["feasible"] is False
    assert "turnover" in infeasible["violations"]
