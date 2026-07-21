"""Cox-Ross-Rubinstein binomial American option pricer."""

from __future__ import annotations

import math
from typing import Literal

OptionType = Literal["call", "put", "C", "P"]


def _normalize_right(option_type: str) -> str:
    token = str(option_type or "").strip().lower()
    if token in {"c", "call"}:
        return "call"
    if token in {"p", "put"}:
        return "put"
    raise ValueError("option_type must be call/put")


def price_american(
    spot: float,
    strike: float,
    t: float,
    r: float,
    q: float,
    sigma: float,
    steps: int,
    option_type: OptionType,
) -> float:
    """CRR American put/call. Raises ValueError when inputs are invalid."""
    if spot <= 0 or strike <= 0:
        raise ValueError("spot and strike must be positive")
    if t <= 0:
        raise ValueError("time to expiry must be positive")
    if sigma <= 0:
        raise ValueError("volatility must be positive")
    if steps < 1:
        raise ValueError("steps must be >= 1")
    right = _normalize_right(option_type)

    dt = t / float(steps)
    u = math.exp(sigma * math.sqrt(dt))
    d = 1.0 / u
    growth = math.exp((r - q) * dt)
    p = (growth - d) / (u - d)
    if not (0.0 < p < 1.0):
        raise ValueError("invalid risk-neutral probability for CRR tree")
    disc = math.exp(-r * dt)

    # Terminal payoff
    values = [0.0] * (steps + 1)
    for i in range(steps + 1):
        st = spot * (u ** (steps - i)) * (d ** i)
        if right == "put":
            values[i] = max(strike - st, 0.0)
        else:
            values[i] = max(st - strike, 0.0)

    for step in range(steps - 1, -1, -1):
        nxt = [0.0] * (step + 1)
        for i in range(step + 1):
            cont = disc * (p * values[i] + (1.0 - p) * values[i + 1])
            st = spot * (u ** (step - i)) * (d ** i)
            if right == "put":
                exercise = max(strike - st, 0.0)
            else:
                exercise = max(st - strike, 0.0)
            nxt[i] = max(cont, exercise)
        values = nxt
    return float(values[0])


def try_price_american(
    spot: float,
    strike: float,
    t: float,
    r: float,
    q: float,
    sigma: float,
    steps: int,
    option_type: OptionType,
) -> tuple[float | None, list[str]]:
    """Return (price, exclusions). Withholds on invalid inputs instead of raising."""
    try:
        return price_american(spot, strike, t, r, q, sigma, steps, option_type), []
    except ValueError as exc:
        return None, [f"american_pricer_invalid:{exc}"]
