from __future__ import annotations

from datetime import date

from app.services.portfolio_construction.tax_transition import (
    TaxLotTransitionInput,
    TaxTransitionRequest,
    build_tax_lot_transition_inputs_from_open_lots,
    evaluate_tax_transition,
    lot_marginal_tax_rate,
    symbol_sell_tax_rate_and_capacity,
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


def test_blocked_lots_cannot_fund_sells():
    lots = [
        TaxLotTransitionInput(
            lot_id="blocked",
            symbol="AAPL",
            quantity=10,
            cost_basis=1000,
            market_value=2000,
            unrealized_gain_loss=1000,
            holding_period_days=100,
            is_wash_sale_blocked=True,
        ),
        TaxLotTransitionInput(
            lot_id="ok",
            symbol="AAPL",
            quantity=10,
            cost_basis=1000,
            market_value=2000,
            unrealized_gain_loss=1000,
            holding_period_days=400,
        ),
    ]
    result = evaluate_tax_transition(
        TaxTransitionRequest(
            account_type="Taxable",
            jurisdiction="US",
            tax_lots=lots,
            tax_budget=None,
        )
    )
    assert "blocked" in result.blocked_lots
    assert "ok" in result.sell_candidates
    rate, fraction = symbol_sell_tax_rate_and_capacity(
        symbol="AAPL",
        market_value=4000,
        lots=lots,
        transition=result,
        account_type="Taxable",
        jurisdiction="US",
    )
    assert fraction == 0.5
    assert abs(rate - (1000 * 0.15 / 4000)) < 1e-9


def test_us_long_term_rate_not_flat_25_percent():
    lot = TaxLotTransitionInput(
        lot_id="lt",
        symbol="MSFT",
        quantity=1,
        cost_basis=100,
        market_value=200,
        unrealized_gain_loss=100,
        holding_period_days=400,
    )
    assert lot_marginal_tax_rate(lot, account_type="Taxable", jurisdiction="US") == 0.15


def test_build_transition_inputs_from_open_lots():
    class _Lot:
        symbol = "AAA"
        con_id = 1
        quantity = 10
        cost_basis_per_share = 50.0
        acquired_date = date(2024, 1, 1)

    inputs = build_tax_lot_transition_inputs_from_open_lots(
        [_Lot()],
        marks_by_symbol={"AAA": 60.0},
        as_of=date(2025, 1, 1),
    )
    assert len(inputs) == 1
    assert inputs[0].unrealized_gain_loss == 100.0
    assert inputs[0].holding_period_days == 366
