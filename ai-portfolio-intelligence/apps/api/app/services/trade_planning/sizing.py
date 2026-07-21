"""Position sizing (plan §9.2).

Deterministic sizing across several methods. When a required input is missing the
method returns a zero size plus an explicit invalidating assumption — it never
fabricates a size from absent data (§23 no-fabrication).
"""

from __future__ import annotations

from app.schemas.trade_plan import SizingMethod, SizingResult, TradePlan


def _weight_after(notional: float, portfolio_value: float | None) -> float | None:
    if not portfolio_value or portfolio_value <= 0:
        return None
    return round(100.0 * notional / portfolio_value, 4)


def compute_position_size(
    plan: TradePlan,
    *,
    price: float | None,
    portfolio_value: float | None = None,
    atr: float | None = None,
    volatility: float | None = None,
    scenario_loss_per_share: float | None = None,
) -> SizingResult:
    method = plan.sizing_method or SizingMethod.USER_ENTERED
    assumptions: list[str] = []
    inputs: dict[str, object] = {
        "price": price,
        "portfolio_value": portfolio_value,
        "atr": atr,
        "volatility": volatility,
        "risk_budget_pct": plan.risk_budget_pct,
    }
    quantity = 0.0

    def risk_budget_dollars() -> float | None:
        if plan.risk_budget_pct is None or not portfolio_value:
            return None
        return abs(plan.risk_budget_pct) / 100.0 * portfolio_value

    entry = plan.entry_high or plan.entry_low or price

    if method == SizingMethod.USER_ENTERED:
        quantity = plan.proposed_quantity or 0.0
        if plan.proposed_quantity is None:
            assumptions.append("no user quantity provided")

    elif method == SizingMethod.MAX_LOSS:
        risk_per_share = None
        if entry is not None and plan.invalidation_price is not None:
            risk_per_share = abs(entry - plan.invalidation_price)
        budget = plan.maximum_loss if plan.maximum_loss is not None else risk_budget_dollars()
        if not risk_per_share:
            assumptions.append("entry and invalidation price required for max-loss sizing")
        elif budget is None:
            assumptions.append("maximum_loss or risk_budget_pct + portfolio_value required")
        else:
            quantity = budget / risk_per_share

    elif method == SizingMethod.ATR:
        budget = risk_budget_dollars()
        if not atr:
            assumptions.append("ATR required for ATR-based sizing")
        elif budget is None:
            assumptions.append("risk_budget_pct + portfolio_value required")
        else:
            quantity = budget / atr

    elif method == SizingMethod.VOLATILITY:
        budget = risk_budget_dollars()
        if not volatility or not price:
            assumptions.append("volatility and price required for volatility sizing")
        elif budget is None:
            assumptions.append("risk_budget_pct + portfolio_value required")
        else:
            quantity = budget / (volatility * price)

    elif method == SizingMethod.FIXED_PERCENT:
        if plan.risk_budget_pct is None or not portfolio_value or not price:
            assumptions.append("risk_budget_pct, portfolio_value and price required")
        else:
            notional = abs(plan.risk_budget_pct) / 100.0 * portfolio_value
            quantity = notional / price

    elif method == SizingMethod.SCENARIO_LOSS:
        budget = plan.maximum_loss if plan.maximum_loss is not None else risk_budget_dollars()
        if not scenario_loss_per_share:
            assumptions.append("scenario_loss_per_share required for scenario-loss sizing")
        elif budget is None:
            assumptions.append("maximum_loss or risk_budget_pct + portfolio_value required")
        else:
            quantity = budget / scenario_loss_per_share

    elif method == SizingMethod.RISK_CONTRIBUTION:
        assumptions.append(
            "risk-contribution sizing requires the portfolio covariance/risk engine; not yet wired"
        )

    quantity = max(0.0, round(quantity, 4))
    notional = round(quantity * price, 2) if price else 0.0
    if entry is not None and plan.invalidation_price is not None:
        max_loss = round(quantity * abs(entry - plan.invalidation_price), 2)
    else:
        max_loss = plan.maximum_loss or 0.0

    return SizingResult(
        method=method,
        proposed_quantity=quantity,
        proposed_notional=notional,
        maximum_loss=max_loss,
        position_weight_after_pct=_weight_after(notional, portfolio_value),
        invalidating_assumptions=assumptions,
        inputs=inputs,
    )
