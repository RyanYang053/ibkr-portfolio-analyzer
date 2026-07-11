from __future__ import annotations

from app.services.portfolio_construction.tax_transition import (
    TaxLotTransitionInput,
    TaxTransitionRequest,
    evaluate_tax_transition,
)


def test_tax_transition_blocks_lots_when_budget_exceeded():
    request = TaxTransitionRequest(
        account_type="Taxable",
        jurisdiction="US",
        tax_budget=100.0,
        tax_lots=[
            TaxLotTransitionInput(
                lot_id="lot1",
                symbol="AAPL",
                quantity=10,
                cost_basis=1000,
                market_value=2000,
                unrealized_gain_loss=1000,
                holding_period_days=200,
            ),
            TaxLotTransitionInput(
                lot_id="lot2",
                symbol="MSFT",
                quantity=5,
                cost_basis=500,
                market_value=1500,
                unrealized_gain_loss=1000,
                holding_period_days=400,
            ),
        ],
    )
    result = evaluate_tax_transition(request)
    assert result.after_tax_feasible is False
    assert result.blocked_lots
