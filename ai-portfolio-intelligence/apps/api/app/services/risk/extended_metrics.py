"""Extended risk/return metrics.

Deterministic, closed-form measures that complement the core Sharpe/Sortino/VaR
set already computed in :mod:`app.services.risk.advanced_risk`. All functions take
a series of periodic (daily) simple returns expressed as fractions (0.01 == 1%) and
return a plain ``float`` ratio/fraction or ``None`` when the input is degenerate.

These are pure functions (no I/O, no external dependencies beyond the stdlib) so the
presentation layer decides units — e.g. drawdown-family fractions are multiplied by
100 for percentage display, mirroring ``ulcer_index``.

References (formulas are public/standard; implemented independently):
- Omega ratio: Keating & Shadwick (2002).
- Tail ratio / gain-to-pain / capture ratios: empyrical (Apache-2.0) definitions.
- Conditional Drawdown at Risk (CDaR): Chekhlov, Uryasev & Zabarankin (2005).
"""

from __future__ import annotations

import math
from statistics import fmean

TRADING_DAYS = 252


def _percentile(values: list[float], q: float) -> float | None:
    """Linear-interpolation percentile (numpy default method); ``q`` in [0, 100]."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (q / 100.0) * (len(ordered) - 1)
    low = math.floor(rank)
    frac = rank - low
    if low + 1 >= len(ordered):
        return ordered[-1]
    return ordered[low] + frac * (ordered[low + 1] - ordered[low])


def omega_ratio(returns: list[float], required_return_annual: float = 0.0) -> float | None:
    """Probability-weighted gains over losses relative to a threshold return.

    The annual threshold is de-annualised geometrically to a per-period hurdle.
    Returns ``None`` when there are no returns below the threshold (undefined).
    """
    if not returns:
        return None
    threshold = (1.0 + required_return_annual) ** (1.0 / TRADING_DAYS) - 1.0
    gains = 0.0
    losses = 0.0
    for value in returns:
        diff = value - threshold
        if diff >= 0:
            gains += diff
        else:
            losses -= diff
    if losses <= 0:
        return None
    return gains / losses


def tail_ratio(returns: list[float]) -> float | None:
    """Ratio of the right-tail (95th pct) to the left-tail (5th pct) magnitude.

    A value of 1.0 is symmetric; >1 means a fatter right (gain) tail.
    """
    if len(returns) < 2:
        return None
    right = _percentile(returns, 95.0)
    left = _percentile(returns, 5.0)
    if right is None or left is None or left == 0.0:
        return None
    denom = abs(left)
    if denom == 0.0:
        return None
    return abs(right) / denom


def gain_to_pain_ratio(returns: list[float]) -> float | None:
    """Sum of all returns divided by the absolute sum of the negative returns."""
    if not returns:
        return None
    pain = -sum(value for value in returns if value < 0)
    if pain <= 0:
        return None
    return sum(returns) / pain


def profit_factor(returns: list[float]) -> float | None:
    """Gross gains divided by gross losses (absolute)."""
    if not returns:
        return None
    gains = sum(value for value in returns if value > 0)
    losses = -sum(value for value in returns if value < 0)
    if losses <= 0:
        return None
    return gains / losses


def _drawdown_series(returns: list[float]) -> list[float]:
    """Positive drawdown fractions of a compounded equity curve (0.0 == at peak)."""
    equity = 1.0
    peak = 1.0
    drawdowns: list[float] = []
    for value in returns:
        equity *= 1.0 + value
        peak = max(peak, equity)
        drawdowns.append((peak - equity) / peak if peak > 0 else 0.0)
    return drawdowns


def pain_index(returns: list[float]) -> float | None:
    """Mean depth of drawdown across the period (linear analogue of the ulcer index)."""
    if not returns:
        return None
    return fmean(_drawdown_series(returns))


def conditional_drawdown_at_risk(returns: list[float], confidence: float = 0.95) -> float | None:
    """Average of the worst ``(1 - confidence)`` tail of the drawdown distribution."""
    if not returns or not 0.0 < confidence < 1.0:
        return None
    drawdowns = sorted(_drawdown_series(returns), reverse=True)
    if not drawdowns:
        return None
    tail = max(1, math.ceil((1.0 - confidence) * len(drawdowns)))
    return fmean(drawdowns[:tail])


def _cumulative_return(returns: list[float]) -> float:
    equity = 1.0
    for value in returns:
        equity *= 1.0 + value
    return equity - 1.0


def up_capture(returns: list[float], benchmark: list[float]) -> float | None:
    """Compounded return in benchmark-up periods relative to the benchmark's."""
    paired = [(r, b) for r, b in zip(returns, benchmark, strict=False) if b > 0]
    if not paired:
        return None
    bench = _cumulative_return([b for _, b in paired])
    if bench == 0.0:
        return None
    return _cumulative_return([r for r, _ in paired]) / bench


def down_capture(returns: list[float], benchmark: list[float]) -> float | None:
    """Compounded return in benchmark-down periods relative to the benchmark's."""
    paired = [(r, b) for r, b in zip(returns, benchmark, strict=False) if b < 0]
    if not paired:
        return None
    bench = _cumulative_return([b for _, b in paired])
    if bench == 0.0:
        return None
    return _cumulative_return([r for r, _ in paired]) / bench


def up_down_capture(returns: list[float], benchmark: list[float]) -> float | None:
    """Up-capture divided by down-capture (>1 is a favourable asymmetry)."""
    up = up_capture(returns, benchmark)
    down = down_capture(returns, benchmark)
    if up is None or down is None or down == 0.0:
        return None
    return up / down


def batting_average(returns: list[float], benchmark: list[float]) -> float | None:
    """Fraction of periods where the portfolio return beat the benchmark."""
    paired = list(zip(returns, benchmark, strict=False))
    if not paired:
        return None
    wins = sum(1 for r, b in paired if r > b)
    return wins / len(paired)
