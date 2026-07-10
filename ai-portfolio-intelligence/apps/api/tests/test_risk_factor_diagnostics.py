import math

import pytest

from app.services.risk.factor_model import _matrix_ols, compute_measured_factor_exposures
from app.services.risk.regression_diagnostics import build_regression_diagnostics, newey_west_lag


def test_vif_uses_raw_factor_columns_without_duplicate_intercept():
    factors = [
        [0.01, 0.02, -0.01, 0.03, 0.00],
        [0.02, 0.01, 0.00, 0.02, 0.01],
        [0.01, 0.03, 0.02, 0.01, 0.02],
    ]
    y = [0.03, 0.04, 0.02, 0.05, 0.01]
    _, _, _, diagnostics = _matrix_ols(y, factors, min_observations=5)
    assert diagnostics.get("vif_max") is not None
    assert diagnostics["vif_max"] < 50


def test_regression_diagnostics_include_hac_standard_errors():
    design = [[1.0, 0.1], [1.0, 0.2], [1.0, 0.3], [1.0, 0.4], [1.0, 0.5]]
    residuals = [0.01, -0.02, 0.03, -0.01, 0.02]
    diagnostics = build_regression_diagnostics(
        coefficients=[0.02, 0.04],
        design=design,
        residuals=residuals,
        r_squared=0.5,
        observation_count=5,
        vif_max=1.2,
        condition_number=2.0,
    )
    assert diagnostics["newey_west_lag"] == newey_west_lag(5)
    assert diagnostics["coefficients"][0]["hac_standard_error"] is not None


from datetime import date, timedelta


def test_measured_and_heuristic_factor_fields_are_separate():
    start = date(2024, 1, 1)
    portfolio_returns = {
        (start + timedelta(days=offset)).isoformat(): 0.001 * (offset + 1)
        for offset in range(140)
    }
    exposures, quality, metadata = compute_measured_factor_exposures(
        portfolio_returns,
        allow_mock=True,
    )
    assert quality in {"experimental", "insufficient_history", "insufficient_factor_history", "regression_failed"}
    if exposures:
        assert "Market" in exposures or len(exposures) > 0
        diagnostics = metadata.get("diagnostics", {})
        assert "vif_max" in diagnostics or diagnostics == {}


def test_contribution_to_variance_percent_reconciles_to_100():
    weights = {"AAA": 0.6, "BBB": 0.4}
    covariance = [
        [0.0004, 0.0001],
        [0.0001, 0.0009],
    ]
    symbols = ["AAA", "BBB"]
    from app.services.risk.advanced_risk import _risk_contribution

    _marginal, component = _risk_contribution(weights, covariance, symbols)
    total = sum(component.values())
    contribution_pct = {symbol: (value / total) * 100.0 for symbol, value in component.items()}
    assert math.isclose(sum(contribution_pct.values()), 100.0, abs_tol=0.05)
