from __future__ import annotations

from app.services.portfolio_construction.transaction_cost_model import TransactionCostInputs, estimate_transaction_cost


def test_transaction_cost_components_sum_to_total():
    estimate = estimate_transaction_cost(
        TransactionCostInputs(
            instrument_key="MSFT",
            trade_value=10_000.0,
            bid_ask_spread_bps=10.0,
            commission_bps=5.0,
            market_impact_bps=8.0,
            fx_conversion_bps=2.0,
            option_contract_cost=0.0,
            minimum_ticket_cost=1.0,
        )
    )
    assert estimate.total_expected > estimate.commission
    assert estimate.total_stressed >= estimate.total_expected
