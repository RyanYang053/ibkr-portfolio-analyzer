from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TransactionCostInputs:
    instrument_key: str
    trade_value: float
    bid_ask_spread_bps: float
    commission_bps: float
    market_impact_bps: float
    fx_conversion_bps: float
    option_contract_cost: float
    minimum_ticket_cost: float
    is_option: bool = False


@dataclass(frozen=True)
class TransactionCostEstimate:
    commission: float
    half_spread: float
    market_impact: float
    fx_conversion: float
    option_contract_cost: float
    minimum_ticket: float
    total_expected: float
    total_stressed: float


def estimate_transaction_cost(inputs: TransactionCostInputs, *, stress_multiplier: float = 1.5) -> TransactionCostEstimate:
    notional = abs(inputs.trade_value)
    commission = notional * inputs.commission_bps / 10_000.0
    half_spread = notional * (inputs.bid_ask_spread_bps / 2.0) / 10_000.0
    market_impact = notional * inputs.market_impact_bps / 10_000.0
    fx_conversion = notional * inputs.fx_conversion_bps / 10_000.0
    option_cost = inputs.option_contract_cost if inputs.is_option else 0.0
    minimum_ticket = inputs.minimum_ticket_cost if notional > 0 else 0.0
    expected = commission + half_spread + market_impact + fx_conversion + option_cost + minimum_ticket
    stressed = expected * stress_multiplier
    return TransactionCostEstimate(
        commission=commission,
        half_spread=half_spread,
        market_impact=market_impact,
        fx_conversion=fx_conversion,
        option_contract_cost=option_cost,
        minimum_ticket=minimum_ticket,
        total_expected=expected,
        total_stressed=stressed,
    )


def portfolio_turnover_cost(
    current_weights: list[float],
    target_weights: list[float],
    *,
    total_portfolio_value: float,
    cost_inputs: list[TransactionCostInputs],
) -> TransactionCostEstimate:
    totals = TransactionCostEstimate(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    for index, (current, target) in enumerate(zip(current_weights, target_weights, strict=False)):
        delta = abs(target - current) * total_portfolio_value
        if delta <= 0:
            continue
        inputs = cost_inputs[index]
        estimate = estimate_transaction_cost(
            TransactionCostInputs(
                instrument_key=inputs.instrument_key,
                trade_value=delta,
                bid_ask_spread_bps=inputs.bid_ask_spread_bps,
                commission_bps=inputs.commission_bps,
                market_impact_bps=inputs.market_impact_bps,
                fx_conversion_bps=inputs.fx_conversion_bps,
                option_contract_cost=inputs.option_contract_cost,
                minimum_ticket_cost=inputs.minimum_ticket_cost,
                is_option=inputs.is_option,
            )
        )
        totals = TransactionCostEstimate(
            commission=totals.commission + estimate.commission,
            half_spread=totals.half_spread + estimate.half_spread,
            market_impact=totals.market_impact + estimate.market_impact,
            fx_conversion=totals.fx_conversion + estimate.fx_conversion,
            option_contract_cost=totals.option_contract_cost + estimate.option_contract_cost,
            minimum_ticket=totals.minimum_ticket + estimate.minimum_ticket,
            total_expected=totals.total_expected + estimate.total_expected,
            total_stressed=totals.total_stressed + estimate.total_stressed,
        )
    return totals
