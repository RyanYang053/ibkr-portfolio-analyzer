"""Whole-share discrete allocation (decision-support only, never an order).

Converts a set of target weights into integer share counts against latest prices and
an available budget, using the greedy algorithm popularised by PyPortfolioOpt: floor
each holding to whole shares, then spend the remaining cash one share at a time on the
name that is currently most underweight versus its target.

This is a *reviewable suggestion* — it emits "to reach these weights, hold N shares of
X" for a human to consider. It has no connection to any order-submission path, honouring
the product's no-trading contract.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

_TOLERANCE = 1e-6


@dataclass(frozen=True)
class DiscreteAllocation:
    shares: dict[str, int]
    leftover_cash: float
    allocated_value: float


def greedy_whole_share_allocation(
    target_weights: dict[str, float],
    latest_prices: dict[str, float],
    total_value: float,
) -> DiscreteAllocation:
    """Long-only greedy whole-share allocation.

    Args:
        target_weights: symbol -> target weight (0..1). Non-positive weights are ignored;
            the total of positive weights must not exceed 1.0.
        latest_prices: symbol -> price (> 0) for every positively-weighted symbol.
        total_value: portfolio value to allocate (> 0).

    Raises:
        ValueError: on a non-positive budget, missing/non-positive price, negative weight,
            or target weights summing above 100%.
    """
    if not math.isfinite(total_value) or total_value <= 0:
        raise ValueError("total_value must be a finite positive number")

    active: dict[str, float] = {}
    for symbol, weight in target_weights.items():
        if weight < 0:
            raise ValueError(f"negative target weight for {symbol}; allocation is long-only")
        if weight <= 0:
            continue
        price = latest_prices.get(symbol)
        if price is None or not math.isfinite(price) or price <= 0:
            raise ValueError(f"missing or non-positive price for {symbol}")
        active[symbol] = weight

    if sum(active.values()) > 1.0 + _TOLERANCE:
        raise ValueError("target weights exceed 100%")

    shares = {symbol: 0 for symbol in active}
    available = total_value

    # Floor pass: whole shares that fit inside each name's target dollar budget.
    for symbol, weight in active.items():
        price = latest_prices[symbol]
        count = int((weight * total_value) // price)
        shares[symbol] = count
        available -= count * price

    # Greedy pass: spend remaining cash on the most-underweight affordable name.
    while True:
        best_symbol: str | None = None
        best_deficit = _TOLERANCE
        for symbol, weight in active.items():
            price = latest_prices[symbol]
            if price > available:
                continue
            current_weight = shares[symbol] * price / total_value
            deficit = weight - current_weight
            if deficit > best_deficit:
                best_deficit = deficit
                best_symbol = symbol
        if best_symbol is None:
            break
        shares[best_symbol] += 1
        available -= latest_prices[best_symbol]

    allocated = total_value - available
    return DiscreteAllocation(
        shares={symbol: count for symbol, count in shares.items() if count > 0},
        leftover_cash=available,
        allocated_value=allocated,
    )
