"""Named fundamental scoring models (distress, forensic, valuation anchors).

These complement the qualitative ``investor_lenses`` (Graham/Piotroski/Greenblatt
style *quality* scores) with the standard *distress* and *manipulation* models plus
the Graham Number valuation anchor and DuPont/WACC decompositions.

All functions are pure and deterministic. Formulas are public and implemented
independently:
- Altman Z-score: Altman (1968), manufacturing coefficients.
- Beneish M-score: Beneish (1999), 8-variable model.
- Graham Number: Graham, *The Intelligent Investor*.

Only :func:`graham_number` (and net margin) can be sourced from the current
FundamentalSnapshot; Altman/Beneish/DuPont/WACC require balance-sheet line items
that arrive with the EDGAR statement upgrade — they take explicit inputs so they are
ready to wire without fabricating data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

# --- Altman Z-score (bankruptcy distress) ---------------------------------------


@dataclass(frozen=True)
class AltmanInputs:
    working_capital: float
    retained_earnings: float
    ebit: float
    market_value_equity: float
    total_liabilities: float
    sales: float
    total_assets: float


def altman_z_score(inputs: AltmanInputs) -> float | None:
    """Classic (manufacturing) Altman Z. Higher is safer; see :func:`altman_zone`."""
    if inputs.total_assets <= 0 or inputs.total_liabilities <= 0:
        return None
    x1 = inputs.working_capital / inputs.total_assets
    x2 = inputs.retained_earnings / inputs.total_assets
    x3 = inputs.ebit / inputs.total_assets
    x4 = inputs.market_value_equity / inputs.total_liabilities
    x5 = inputs.sales / inputs.total_assets
    return 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5


def altman_zone(z_score: float | None) -> str:
    """Interpret a Z-score: 'distress' (<1.81), 'grey' (1.81-2.99), 'safe' (>2.99)."""
    if z_score is None:
        return "unknown"
    if z_score < 1.81:
        return "distress"
    if z_score <= 2.99:
        return "grey"
    return "safe"


# --- Beneish M-score (earnings-manipulation likelihood) -------------------------


@dataclass(frozen=True)
class BeneishPeriod:
    receivables: float
    sales: float
    cost_of_goods_sold: float
    current_assets: float
    ppe: float
    total_assets: float
    depreciation: float
    sga: float
    total_debt: float
    net_income_continuing: float
    cash_from_operations: float


def _safe_div(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def beneish_m_score(current: BeneishPeriod, prior: BeneishPeriod) -> float | None:
    """8-variable Beneish M-score. M > -1.78 flags a likely earnings manipulator."""
    dsri = _safe_div(
        _safe_div(current.receivables, current.sales) or 0.0,
        _safe_div(prior.receivables, prior.sales) or 0.0,
    )
    gm_current = _safe_div(current.sales - current.cost_of_goods_sold, current.sales)
    gm_prior = _safe_div(prior.sales - prior.cost_of_goods_sold, prior.sales)
    gmi = _safe_div(gm_prior or 0.0, gm_current or 0.0)
    aqi_current = 1.0 - _safe_div(current.current_assets + current.ppe, current.total_assets)  # type: ignore[operator]
    aqi_prior = 1.0 - _safe_div(prior.current_assets + prior.ppe, prior.total_assets)  # type: ignore[operator]
    aqi = _safe_div(aqi_current, aqi_prior)
    sgi = _safe_div(current.sales, prior.sales)
    dep_current = _safe_div(current.depreciation, current.depreciation + current.ppe)
    dep_prior = _safe_div(prior.depreciation, prior.depreciation + prior.ppe)
    depi = _safe_div(dep_prior or 0.0, dep_current or 0.0)
    sgai = _safe_div(
        _safe_div(current.sga, current.sales) or 0.0,
        _safe_div(prior.sga, prior.sales) or 0.0,
    )
    lvgi = _safe_div(
        _safe_div(current.total_debt, current.total_assets) or 0.0,
        _safe_div(prior.total_debt, prior.total_assets) or 0.0,
    )
    tata = _safe_div(current.net_income_continuing - current.cash_from_operations, current.total_assets)

    parts = [dsri, gmi, aqi, sgi, depi, sgai, lvgi, tata]
    if any(part is None for part in parts):
        return None
    return (
        -4.84
        + 0.920 * dsri  # type: ignore[operator]
        + 0.528 * gmi  # type: ignore[operator]
        + 0.404 * aqi  # type: ignore[operator]
        + 0.892 * sgi  # type: ignore[operator]
        + 0.115 * depi  # type: ignore[operator]
        - 0.172 * sgai  # type: ignore[operator]
        + 4.679 * tata  # type: ignore[operator]
        - 0.327 * lvgi  # type: ignore[operator]
    )


def beneish_manipulation_flag(m_score: float | None) -> bool | None:
    if m_score is None:
        return None
    return m_score > -1.78


# --- Graham Number, DuPont, WACC ------------------------------------------------


def graham_number(eps: float | None, book_value_per_share: float | None) -> float | None:
    """Graham's fair-value anchor: sqrt(22.5 * EPS * book value per share)."""
    if eps is None or book_value_per_share is None or eps <= 0 or book_value_per_share <= 0:
        return None
    return math.sqrt(22.5 * eps * book_value_per_share)


def dupont_decomposition(
    net_income: float, revenue: float, total_assets: float, equity: float
) -> dict[str, float] | None:
    """Three-step DuPont: ROE = net margin * asset turnover * equity multiplier."""
    if revenue == 0 or total_assets == 0 or equity == 0:
        return None
    net_margin = net_income / revenue
    asset_turnover = revenue / total_assets
    equity_multiplier = total_assets / equity
    return {
        "net_margin": net_margin,
        "asset_turnover": asset_turnover,
        "equity_multiplier": equity_multiplier,
        "roe": net_margin * asset_turnover * equity_multiplier,
    }


def wacc(
    equity_value: float,
    debt_value: float,
    cost_of_equity: float,
    cost_of_debt: float,
    tax_rate: float,
) -> float | None:
    """Weighted average cost of capital with an after-tax debt component."""
    total = equity_value + debt_value
    if total <= 0:
        return None
    w_equity = equity_value / total
    w_debt = debt_value / total
    return w_equity * cost_of_equity + w_debt * cost_of_debt * (1.0 - tax_rate)


# --- Adapter: what today's FundamentalSnapshot can support ----------------------


def scores_from_snapshot(fundamentals: Any) -> dict[str, float | None]:
    """Compute the models the current snapshot has inputs for (Graham Number, net margin).

    Altman/Beneish/DuPont/WACC require balance-sheet line items not yet on the snapshot
    (they land with the EDGAR statement upgrade); they are omitted rather than guessed.
    """
    net_income = getattr(fundamentals, "net_income_common", None)
    revenue = getattr(fundamentals, "revenue", None)
    diluted_shares = getattr(fundamentals, "diluted_shares", None)
    book_per_share = getattr(fundamentals, "tangible_book_per_share", None)

    eps = net_income / diluted_shares if net_income is not None and diluted_shares else None
    net_margin = net_income / revenue if net_income is not None and revenue else None
    return {
        "graham_number": graham_number(eps, book_per_share),
        "net_margin": net_margin,
    }
