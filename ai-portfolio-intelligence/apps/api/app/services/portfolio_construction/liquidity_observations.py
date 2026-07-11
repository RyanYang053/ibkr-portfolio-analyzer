from __future__ import annotations

import statistics
from typing import Any

from app.schemas.domain import Position
from app.services.portfolio_construction.liquidity_model import LiquidityInputs


def _history_closes(history: list[dict[str, Any]]) -> list[float]:
    closes: list[float] = []
    for row in history:
        close = row.get("close")
        if close is not None and float(close) > 0:
            closes.append(float(close))
    return closes


def _history_dollar_volumes(history: list[dict[str, Any]]) -> list[float]:
    volumes: list[float] = []
    for row in history:
        close = row.get("close")
        shares = row.get("volume")
        if close is None or shares is None:
            continue
        shares_value = float(shares)
        if shares_value <= 0:
            continue
        volumes.append(float(close) * shares_value)
    return volumes


def _spread_bps_from_history(history: list[dict[str, Any]]) -> float | None:
    spreads: list[float] = []
    for row in history[-20:]:
        high = row.get("high")
        low = row.get("low")
        close = row.get("close")
        if high is None or low is None or close is None:
            continue
        close_value = float(close)
        if close_value <= 0:
            continue
        spreads.append((float(high) - float(low)) / close_value * 10_000.0)
    if len(spreads) < 5:
        return None
    return float(statistics.median(spreads))


def resolve_liquidity_inputs(
    position: Position,
    *,
    history: list[dict[str, Any]],
    daily_returns: list[float],
    participation_rate: float,
    max_exit_days: float,
    minimum_trade_value: float,
) -> LiquidityInputs | None:
    dollar_volumes = _history_dollar_volumes(history)
    if len(dollar_volumes) < 10:
        return None

    spread_bps = _spread_bps_from_history(history)
    if spread_bps is None:
        return None

    if len(daily_returns) < 20:
        return None
    volatility_20d = float(statistics.pstdev(daily_returns[-20:]) * (252**0.5))
    if volatility_20d <= 0:
        return None

    median_adv = float(statistics.median(dollar_volumes[-20:]))
    if median_adv <= 0:
        return None

    return LiquidityInputs(
        instrument_key=position.symbol.upper(),
        median_daily_dollar_volume_20d=median_adv,
        bid_ask_spread_bps=spread_bps,
        volatility_20d=volatility_20d,
        participation_rate=participation_rate,
        max_exit_days=max_exit_days,
        minimum_trade_value=minimum_trade_value,
    )
