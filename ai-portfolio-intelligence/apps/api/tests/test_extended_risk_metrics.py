"""Unit tests for app.services.risk.extended_metrics (closed-form, exact vectors)."""

from __future__ import annotations

import pytest

from app.services.risk import extended_metrics as em

RETURNS = [0.10, -0.05, 0.03, -0.02, 0.04]
BENCHMARK = [0.08, -0.04, 0.01, -0.03, 0.02]


def test_percentile_linear_interpolation():
    assert em._percentile([-0.05, -0.02, 0.03, 0.04, 0.10], 95.0) == pytest.approx(0.088)
    assert em._percentile([-0.05, -0.02, 0.03, 0.04, 0.10], 5.0) == pytest.approx(-0.044)


def test_omega_ratio_equals_profit_factor_at_zero_threshold():
    # gains 0.17 / losses 0.07
    assert em.omega_ratio(RETURNS) == pytest.approx(0.17 / 0.07)
    assert em.profit_factor(RETURNS) == pytest.approx(0.17 / 0.07)


def test_omega_ratio_undefined_without_losses():
    assert em.omega_ratio([0.01, 0.02, 0.03]) is None


def test_tail_ratio():
    assert em.tail_ratio(RETURNS) == pytest.approx(0.088 / 0.044)  # == 2.0
    assert em.tail_ratio([0.01]) is None


def test_gain_to_pain_ratio():
    assert em.gain_to_pain_ratio(RETURNS) == pytest.approx(0.10 / 0.07)
    assert em.gain_to_pain_ratio([0.01, 0.02]) is None


def test_pain_index_and_cdar():
    assert em.pain_index(RETURNS) == pytest.approx(0.02305656, abs=1e-6)
    # worst 1 of 5 drawdowns at 95% confidence is the 5% loss period
    assert em.conditional_drawdown_at_risk(RETURNS, 0.95) == pytest.approx(0.05, abs=1e-9)
    assert em.conditional_drawdown_at_risk([], 0.95) is None
    assert em.conditional_drawdown_at_risk(RETURNS, 1.0) is None


def test_capture_ratios():
    assert em.up_capture(RETURNS, BENCHMARK) == pytest.approx(0.17832 / 0.112616, rel=1e-6)
    assert em.down_capture(RETURNS, BENCHMARK) == pytest.approx((-0.069) / (-0.0688), rel=1e-6)
    assert em.up_down_capture(RETURNS, BENCHMARK) == pytest.approx(
        (0.17832 / 0.112616) / ((-0.069) / (-0.0688)), rel=1e-6
    )


def test_batting_average():
    assert em.batting_average(RETURNS, BENCHMARK) == pytest.approx(0.8)
    assert em.batting_average([], []) is None


def test_empty_inputs_return_none():
    for fn in (em.omega_ratio, em.tail_ratio, em.gain_to_pain_ratio, em.profit_factor, em.pain_index):
        assert fn([]) is None
