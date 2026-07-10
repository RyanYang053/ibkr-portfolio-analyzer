from datetime import date

import pytest

from app.schemas.domain import Transaction
from app.services.portfolio.performance_returns import _flow_weight, _modified_dietz_interval_return


def test_modified_dietz_uses_remaining_period_weight():
    early_weight = _flow_weight(date(2026, 1, 2), date(2026, 1, 1), date(2026, 1, 15))
    late_weight = _flow_weight(date(2026, 1, 14), date(2026, 1, 1), date(2026, 1, 15))
    assert early_weight > late_weight
    assert early_weight == pytest.approx(13 / 14, rel=1e-6)
    assert late_weight == pytest.approx(1 / 14, rel=1e-6)


def test_modified_dietz_early_deposit_differs_from_reversed_weight_formula():
    transactions = [
        Transaction(
            account_id="TEST-001",
            symbol="CASH",
            trade_date=date(2026, 1, 2),
            action="deposit",
            quantity=1,
            price=5000,
            commission=0,
            currency="USD",
            amount=5000,
        )
    ]
    interval_return = _modified_dietz_interval_return(
        100_000,
        106_000,
        transactions,
        date(2026, 1, 1),
        date(2026, 1, 15),
        "USD",
        lambda _a, _b, _c=None: 1.0,
    )
    reversed_weight_return = 1000 / (100_000 + 5000 * (1 / 14))
    assert interval_return is not None
    assert interval_return != pytest.approx(reversed_weight_return, rel=1e-4)
    assert interval_return == pytest.approx(1000 / (100_000 + 5000 * (13 / 14)), rel=1e-4)


def test_benchmark_weights_withheld_outside_mock():
    from app.services.attribution.benchmark_weights import benchmark_sector_weights_as_of

    assert benchmark_sector_weights_as_of(date.today(), allow_mock=False) is None
    assert benchmark_sector_weights_as_of(date.today(), allow_mock=True)


def test_experimental_optimizer_objective_withheld_for_live_accounts():
    from app.schemas.domain import AccountSummary, InvestmentPolicyStatement, InvestorProfile, Position, utc_now
    from app.services.portfolio_construction.optimizer import generate_portfolio_optimization

    positions = [
        Position(
            account_id="LIVE-001",
            symbol="AAA",
            company_name="AAA",
            asset_class="Equity",
            quantity=100,
            avg_cost=10,
            market_price=12,
            market_value=1200,
            unrealized_pnl=200,
            realized_pnl=0,
            currency="USD",
            exchange="NASDAQ",
            sector="Technology",
            industry="Software",
            portfolio_weight=50,
            stock_type="universal",
            is_etf=False,
            is_speculative=False,
            con_id=1,
            updated_at=utc_now(),
        ),
        Position(
            account_id="LIVE-001",
            symbol="BBB",
            company_name="BBB",
            asset_class="Equity",
            quantity=50,
            avg_cost=20,
            market_price=22,
            market_value=1100,
            unrealized_pnl=100,
            realized_pnl=0,
            currency="USD",
            exchange="NASDAQ",
            sector="Healthcare",
            industry="Biotech",
            portfolio_weight=50,
            stock_type="universal",
            is_etf=False,
            is_speculative=False,
            con_id=2,
            updated_at=utc_now(),
        ),
    ]
    summary = AccountSummary(
        account_id="LIVE-001",
        net_liquidation=2500,
        cash=200,
        buying_power=2000,
        margin_requirement=0,
        excess_liquidity=2000,
        total_unrealized_pnl=300,
        total_realized_pnl=0,
        base_currency="USD",
        data_timestamp=utc_now(),
    )
    policy = InvestmentPolicyStatement(
        target_equity_percent=90,
        target_cash_percent=10,
        target_bond_percent=0,
        minimum_cash=5,
    )
    profile = InvestorProfile(
        objective="Growth",
        time_horizon_years=10,
        risk_tolerance="Medium",
        risk_capacity="Medium",
        liquidity_needs=0.1,
        net_worth_range="250k-1m",
        tax_residency="US",
        account_type="Taxable",
    )
    with pytest.raises(ValueError, match="experimental"):
        generate_portfolio_optimization(positions, summary, policy, profile, objective="hrp")
