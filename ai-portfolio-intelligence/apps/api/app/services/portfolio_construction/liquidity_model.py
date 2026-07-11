from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LiquidityInputs:
    instrument_key: str
    median_daily_dollar_volume_20d: float
    bid_ask_spread_bps: float
    volatility_20d: float
    participation_rate: float
    max_exit_days: float
    minimum_trade_value: float


def maximum_trade_value(inputs: LiquidityInputs) -> float:
    return inputs.median_daily_dollar_volume_20d * inputs.participation_rate * inputs.max_exit_days


def days_to_liquidate(trade_value: float, inputs: LiquidityInputs) -> float | None:
    daily_capacity = inputs.median_daily_dollar_volume_20d * inputs.participation_rate
    if daily_capacity <= 0:
        return None
    return trade_value / daily_capacity


def portfolio_weight_cap(trade_value: float, total_portfolio_value: float) -> float | None:
    if total_portfolio_value <= 0:
        return None
    return trade_value / total_portfolio_value


def liquidity_capacity_weight(
    inputs: LiquidityInputs,
    *,
    total_portfolio_value: float,
    current_weight: float,
) -> float | None:
    if total_portfolio_value <= 0:
        return None
    max_trade = maximum_trade_value(inputs)
    if max_trade <= 0:
        return None
    return current_weight + (max_trade / total_portfolio_value)
