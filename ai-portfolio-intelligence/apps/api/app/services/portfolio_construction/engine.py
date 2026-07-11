from __future__ import annotations

import math
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


PositionKey = tuple[str, int | None]


def _position_key(position: Position) -> PositionKey:
    return position.symbol.upper(), position.con_id


def _position_bucket_key(position: Position) -> str:
    symbol, con_id = _position_key(position)
    if con_id is not None:
        return f"{symbol}:{con_id}"
    return symbol


def generate_rebalance_proposal(
    positions: list[Position],
    summary: AccountSummary,
    policy: InvestmentPolicyStatement,
    profile: InvestorProfile,
) -> RebalanceProposal:
    """Generate a bounded, deterministic rebalance review proposal.

    All values are converted to the account reporting currency before constraints
    and trade notionals are calculated. The output remains a review proposal, not
    an optimizer: tax lots, spreads, commissions, settlement, expected returns,
    and approved replacement instruments are unavailable.
    """
    _validate_policy(policy)
    if not math.isfinite(summary.net_liquidation) or summary.net_liquidation <= 0:
        raise ValueError("Net liquidation must be finite and positive before rebalancing")

    from app.services.broker.ibkr_readonly import get_exchange_rate

    total_value = float(summary.net_liquidation)
    current_cash = float(summary.cash)
    cash_floor = max(policy.minimum_cash, total_value * policy.target_cash_percent / 100.0)

    converted: dict[PositionKey, tuple[Position, float, float]] = {}
    for position in positions:
        key = _position_key(position)
        if key in converted:
            raise ValueError(
                "Duplicate position keys require a conId-aware rebalance proposal schema; refusing to merge distinct contracts."
            )
        rate = float(get_exchange_rate(position.currency, summary.base_currency))
        if not math.isfinite(rate) or rate <= 0:
            raise ValueError(f"Invalid FX rate for {position.currency}/{summary.base_currency}: {rate}")
        market_value_base = float(position.market_value) * rate
        market_price_base = float(position.market_price) * rate
        converted[key] = (position, market_value_base, market_price_base)

    drift = analyze_policy_drift(
        positions,
        current_cash,
        total_value,
        policy,
        base_currency=summary.base_currency,
        fx_resolver=get_exchange_rate,
    )

    long_positions = [
        item
        for item in converted.values()
        if item[0].quantity > 0 and item[1] > 0 and item[2] > 0
    ]
    position_keys = [_position_key(item[0]) for item in long_positions]
    if len(position_keys) != len(set(position_keys)):
        raise ValueError(
            "Duplicate position keys require a conId-aware rebalance proposal schema; refusing to merge distinct contracts."
        )
    by_key = {key: item for key, item in zip(position_keys, long_positions, strict=False)}
    planned_sales: dict[PositionKey, float] = defaultdict(float)
    sale_reasons: dict[PositionKey, list[str]] = defaultdict(list)

    def plan_sale(item: tuple[Position, float, float], requested_value_base: float, reason: str) -> None:
        position, market_value_base, _ = item
        key = _position_key(position)
        if requested_value_base <= 0:
            return
        remaining_value = max(0.0, market_value_base - planned_sales[key])
        sale_value = min(requested_value_base, remaining_value)
        if sale_value < MINIMUM_TRADE_VALUE:
            return
        planned_sales[key] += sale_value
        sale_reasons[key].append(reason)

    for item in long_positions:
        position, market_value_base, _ = item
        if position.is_etf or position.asset_class in {"OPT", "FOP"}:
            continue
        current_weight = market_value_base / total_value * 100.0
        if current_weight > policy.max_single_stock_weight:
            target_value = total_value * policy.max_single_stock_weight / 100.0
            plan_sale(
                item,
                market_value_base - target_value,
                f"Reduce single-name exposure to the {policy.max_single_stock_weight:.2f}% policy limit.",
            )

    speculative = [item for item in long_positions if item[0].is_speculative]
    speculative_value_after_sales = sum(
        max(0.0, market_value_base - planned_sales[_position_key(position)])
        for position, market_value_base, _ in speculative
    )
    speculative_limit_value = total_value * policy.max_speculative_weight / 100.0
    speculative_excess = max(0.0, speculative_value_after_sales - speculative_limit_value)
    if speculative_excess > 0 and speculative_value_after_sales > 0:
        for item in speculative:
            position, market_value_base, _ = item
            remaining = max(0.0, market_value_base - planned_sales[_position_key(position)])
            plan_sale(
                item,
                speculative_excess * remaining / speculative_value_after_sales,
                f"Reduce the speculative basket to the {policy.max_speculative_weight:.2f}% policy limit.",
            )

    required_cash_raise = max(0.0, cash_floor - current_cash)
    cash_from_planned_sales = sum(planned_sales.values())
    additional_cash_needed = max(0.0, required_cash_raise - cash_from_planned_sales)
    equity_drift = float(drift["drifts"]["equity"]["drift"])
    equity_reduction_needed = (
        total_value * equity_drift / 100.0
        if equity_drift > policy.rebalancing_drift_threshold
        else 0.0
    )
    additional_sale_target = max(additional_cash_needed, equity_reduction_needed - cash_from_planned_sales)

    if additional_sale_target > 0:
        candidates = [
            item
            for item in long_positions
            if item[0].asset_class not in {"OPT", "FOP"}
        ]
        candidates = sorted(
            candidates,
            key=lambda item: (
                0 if item[0].is_etf else 1 if not item[0].is_speculative else 2,
                -item[1],
            ),
        )
        remaining_target = additional_sale_target
        for item in candidates:
            position, market_value_base, _ = item
            key = _position_key(position)
            if remaining_target < MINIMUM_TRADE_VALUE:
                break
            available = max(0.0, market_value_base - planned_sales[key])
            if available < MINIMUM_TRADE_VALUE:
                continue
            before = planned_sales[key]
            plan_sale(item, min(available, remaining_target), "Raise the required cash buffer or reduce equity drift.")
            remaining_target -= planned_sales[key] - before

    proposed_trades: list[RebalanceProposalItem] = []
    for key, sale_value_base in sorted(planned_sales.items()):
        position, market_value_base, market_price_base = by_key[key]
        quantity = min(position.quantity, sale_value_base / market_price_base)
        actual_value_base = quantity * market_price_base
        if actual_value_base < MINIMUM_TRADE_VALUE:
            continue
        target_weight = max(0.0, (market_value_base - actual_value_base) / total_value * 100.0)
        proposed_trades.append(
            RebalanceProposalItem(
                symbol=position.symbol,
                con_id=position.con_id,
                current_weight=round(market_value_base / total_value * 100.0, 2),
                target_weight=round(target_weight, 2),
                current_value=round(market_value_base, 2),
                proposed_trade_value=round(-actual_value_base, 2),
                proposed_trade_qty=round(-quantity, 6),
                action="Sell",
                reason=" ".join(dict.fromkeys(sale_reasons[key])),
            )
        )

    if equity_drift < -policy.rebalancing_drift_threshold and current_cash > cash_floor:
        benchmark = policy.benchmark.upper()
        restricted = {item.upper() for item in profile.restrictions}
        benchmark_item = next((item for item in long_positions if item[0].symbol.upper() == benchmark), None)
        if benchmark_item and benchmark not in restricted:
            position, market_value_base, market_price_base = benchmark_item
            available_cash = current_cash - cash_floor
            desired_purchase = min(available_cash, total_value * abs(equity_drift) / 100.0)
            if desired_purchase >= MINIMUM_TRADE_VALUE:
                quantity = desired_purchase / market_price_base
                proposed_trades.append(
                    RebalanceProposalItem(
                        symbol=benchmark,
                        con_id=position.con_id,
                        current_weight=round(market_value_base / total_value * 100.0, 2),
                        target_weight=round((market_value_base + desired_purchase) / total_value * 100.0, 2),
                        current_value=round(market_value_base, 2),
                        proposed_trade_value=round(desired_purchase, 2),
                        proposed_trade_qty=round(quantity, 6),
                        action="Buy",
                        reason=f"Use cash above the policy floor to reduce the {abs(equity_drift):.2f}% equity underweight.",
                    )
                )

    cash_impact = -sum(item.proposed_trade_value for item in proposed_trades)
    if profile.account_type in {"Taxable", "Margin"}:
        sold_symbols = [item.symbol for item in proposed_trades if item.action == "Sell"]
        tax_warning = (
            f"Account type is {profile.account_type}. Sales of {', '.join(sold_symbols)} may realize gains or losses. "
            "Tax lots, FX cost basis, superficial-loss/wash-sale rules, commissions, and settlement are not modeled."
            if sold_symbols
            else "The account is taxable, but this proposal contains no sales. Tax lots and FX cost basis are not modeled."
        )
    else:
        tax_warning = (
            f"Account type is {profile.account_type}. Immediate capital-gains tax is not modeled; account-specific "
            "contribution, withdrawal, and trading rules still require human review."
        )
    if policy.target_bond_percent > 0:
        tax_warning += " Bond purchases are not proposed because no approved bond instrument or live price is configured."

    return RebalanceProposal(
        proposed_trades=proposed_trades,
        cash_impact=round(cash_impact, 2),
        tax_impact_warning=tax_warning,
    )
