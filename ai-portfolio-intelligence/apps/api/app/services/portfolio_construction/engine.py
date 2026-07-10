from __future__ import annotations

from collections import defaultdict

from app.schemas.domain import (
    AccountSummary,
    InvestmentPolicyStatement,
    InvestorProfile,
    Position,
    RebalanceProposal,
    RebalanceProposalItem,
)
from app.services.policy.engine import analyze_policy_drift

MINIMUM_TRADE_VALUE = 100.0


def _validate_policy(policy: InvestmentPolicyStatement) -> None:
    targets = [policy.target_equity_percent, policy.target_cash_percent, policy.target_bond_percent]
    if any(value < 0 or value > 100 for value in targets):
        raise ValueError("Policy target percentages must be between 0 and 100")
    if abs(sum(targets) - 100.0) > 0.5:
        raise ValueError("Equity, cash, and bond policy targets must sum to 100%")
    for value in (
        policy.max_single_stock_weight,
        policy.max_speculative_weight,
        policy.max_sector_weight,
        policy.max_options_exposure,
        policy.rebalancing_drift_threshold,
    ):
        if value < 0 or value > 100:
            raise ValueError("Policy limits must be between 0 and 100")
    if policy.minimum_cash < 0:
        raise ValueError("Minimum cash cannot be negative")


def generate_rebalance_proposal(
    positions: list[Position],
    summary: AccountSummary,
    policy: InvestmentPolicyStatement,
    profile: InvestorProfile,
) -> RebalanceProposal:
    """Generate a bounded, deterministic rebalance review proposal.

    The solver does not invent market prices, does not sell more than a current long
    position, and does not count the same sale twice when satisfying concentration
    and cash-floor constraints. It remains a review proposal rather than an optimizer
    because tax lots, spreads, commissions, settlement, and expected returns are not
    available.
    """

    _validate_policy(policy)
    if summary.net_liquidation <= 0:
        raise ValueError("Net liquidation must be positive before rebalancing")

    total_value = summary.net_liquidation
    current_cash = summary.cash
    cash_floor = max(policy.minimum_cash, total_value * policy.target_cash_percent / 100.0)
    drift = analyze_policy_drift(positions, current_cash, total_value, policy)

    long_positions = [position for position in positions if position.quantity > 0 and position.market_value > 0]
    by_symbol = {position.symbol: position for position in long_positions}
    planned_sales: dict[str, float] = defaultdict(float)
    sale_reasons: dict[str, list[str]] = defaultdict(list)

    def plan_sale(position: Position, requested_value: float, reason: str) -> None:
        if requested_value <= 0:
            return
        remaining_value = max(0.0, position.market_value - planned_sales[position.symbol])
        sale_value = min(requested_value, remaining_value)
        if sale_value < MINIMUM_TRADE_VALUE:
            return
        planned_sales[position.symbol] += sale_value
        sale_reasons[position.symbol].append(reason)

    # 1. Enforce single-name limits.
    for position in long_positions:
        if position.is_etf or position.asset_class in {"OPT", "FOP"}:
            continue
        current_weight = position.market_value / total_value * 100.0
        if current_weight > policy.max_single_stock_weight:
            target_value = total_value * policy.max_single_stock_weight / 100.0
            plan_sale(
                position,
                position.market_value - target_value,
                f"Reduce single-name exposure to the {policy.max_single_stock_weight:.2f}% policy limit.",
            )

    # 2. Enforce the speculative basket after accounting for single-name sales.
    speculative = [position for position in long_positions if position.is_speculative]
    speculative_value_after_planned_sales = sum(
        max(0.0, position.market_value - planned_sales[position.symbol]) for position in speculative
    )
    speculative_limit_value = total_value * policy.max_speculative_weight / 100.0
    speculative_excess = max(0.0, speculative_value_after_planned_sales - speculative_limit_value)
    if speculative_excess > 0 and speculative_value_after_planned_sales > 0:
        for position in speculative:
            remaining = max(0.0, position.market_value - planned_sales[position.symbol])
            share = remaining / speculative_value_after_planned_sales
            plan_sale(
                position,
                speculative_excess * share,
                f"Reduce the speculative basket to the {policy.max_speculative_weight:.2f}% policy limit.",
            )

    # 3. Satisfy the cash floor without double-counting sales already planned.
    required_cash_raise = max(0.0, cash_floor - current_cash)
    cash_from_planned_sales = sum(planned_sales.values())
    additional_cash_needed = max(0.0, required_cash_raise - cash_from_planned_sales)

    # If equity is materially overweight, the equity drift itself may require more
    # selling than the cash floor. Use the larger requirement.
    equity_drift = float(drift["drifts"]["equity"]["drift"])
    equity_reduction_needed = (
        total_value * equity_drift / 100.0
        if equity_drift > policy.rebalancing_drift_threshold
        else 0.0
    )
    additional_sale_target = max(additional_cash_needed, equity_reduction_needed - cash_from_planned_sales)

    if additional_sale_target > 0:
        # Prefer broad ETFs, then largest non-speculative core positions. Positions
        # already partially sold remain eligible up to their unsold market value.
        candidates = sorted(
            long_positions,
            key=lambda position: (
                0 if position.is_etf else 1 if not position.is_speculative else 2,
                -position.market_value,
            ),
        )
        remaining_target = additional_sale_target
        for position in candidates:
            if remaining_target < MINIMUM_TRADE_VALUE:
                break
            available = max(0.0, position.market_value - planned_sales[position.symbol])
            if available < MINIMUM_TRADE_VALUE:
                continue
            sale_value = min(available, remaining_target)
            before = planned_sales[position.symbol]
            plan_sale(position, sale_value, "Raise the required cash buffer or reduce equity drift.")
            remaining_target -= planned_sales[position.symbol] - before

    proposed_trades: list[RebalanceProposalItem] = []
    for symbol, sale_value in sorted(planned_sales.items()):
        position = by_symbol[symbol]
        if position.market_price <= 0:
            continue
        quantity = min(position.quantity, sale_value / position.market_price)
        actual_value = quantity * position.market_price
        if actual_value < MINIMUM_TRADE_VALUE:
            continue
        target_weight = max(0.0, (position.market_value - actual_value) / total_value * 100.0)
        proposed_trades.append(
            RebalanceProposalItem(
                symbol=symbol,
                current_weight=round(position.market_value / total_value * 100.0, 2),
                target_weight=round(target_weight, 2),
                current_value=round(position.market_value, 2),
                proposed_trade_value=round(-actual_value, 2),
                proposed_trade_qty=round(-quantity, 6),
                action="Sell",
                reason=" ".join(dict.fromkeys(sale_reasons[symbol])),
            )
        )

    # 4. Use excess cash to correct a material equity underweight only when a real,
    # currently observed benchmark price exists. Never use a fabricated fallback.
    if equity_drift < -policy.rebalancing_drift_threshold and current_cash > cash_floor:
        benchmark = policy.benchmark.upper()
        restricted = {item.upper() for item in profile.restrictions}
        benchmark_position = next((position for position in long_positions if position.symbol.upper() == benchmark), None)
        if benchmark_position and benchmark_position.market_price > 0 and benchmark not in restricted:
            available_cash = current_cash - cash_floor
            desired_purchase = min(available_cash, total_value * abs(equity_drift) / 100.0)
            if desired_purchase >= MINIMUM_TRADE_VALUE:
                quantity = desired_purchase / benchmark_position.market_price
                proposed_trades.append(
                    RebalanceProposalItem(
                        symbol=benchmark,
                        current_weight=round(benchmark_position.market_value / total_value * 100.0, 2),
                        target_weight=round(
                            (benchmark_position.market_value + desired_purchase) / total_value * 100.0,
                            2,
                        ),
                        current_value=round(benchmark_position.market_value, 2),
                        proposed_trade_value=round(desired_purchase, 2),
                        proposed_trade_qty=round(quantity, 6),
                        action="Buy",
                        reason=f"Use cash above the policy floor to reduce the {abs(equity_drift):.2f}% equity underweight.",
                    )
                )

    cash_impact = -sum(item.proposed_trade_value for item in proposed_trades)

    if profile.account_type in {"Taxable", "Margin"}:
        sold_symbols = [item.symbol for item in proposed_trades if item.action == "Sell"]
        if sold_symbols:
            tax_warning = (
                f"Account type is {profile.account_type}. Sales of {', '.join(sold_symbols)} may realize gains or losses. "
                "Tax lots, superficial-loss/wash-sale rules, commissions, and settlement are not modeled."
            )
        else:
            tax_warning = "The account is taxable, but this proposal contains no sales. Tax lots are not modeled."
    else:
        tax_warning = (
            f"Account type is {profile.account_type}. Immediate capital-gains tax is generally not modeled here; "
            "account-specific contribution, withdrawal, and trading rules still require human review."
        )

    if policy.target_bond_percent > 0:
        tax_warning += " Bond purchases are not proposed because no approved bond instrument or live price is configured."

    return RebalanceProposal(
        proposed_trades=proposed_trades,
        cash_impact=round(cash_impact, 2),
        tax_impact_warning=tax_warning,
    )
