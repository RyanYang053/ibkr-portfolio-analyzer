from __future__ import annotations

import pytest

from app.services.portfolio_construction.liquidity_model import LiquidityInputs, liquidity_capacity_weight, maximum_trade_value


def test_liquidity_capacity_derived_from_participation_and_exit_days():
    inputs = LiquidityInputs(
        instrument_key="AAPL",
        median_daily_dollar_volume_20d=1_000_000.0,
        bid_ask_spread_bps=5.0,
        volatility_20d=0.2,
        participation_rate=0.10,
        max_exit_days=5.0,
        minimum_trade_value=100.0,
    )
    assert maximum_trade_value(inputs) == 500_000.0
    cap = liquidity_capacity_weight(inputs, total_portfolio_value=10_000_000.0, current_weight=0.05)
    assert cap == pytest.approx(0.10, rel=1e-6)
