from datetime import date, timedelta

import pytest

from app.schemas.domain import AccountSummary, Position, Transaction, utc_now
from app.services.portfolio.ledger_coverage import (
    build_ledger_coverage,
    ledger_covers_period,
)
from app.services.portfolio.performance_returns import (
    build_xirr_cash_flows,
    calculate_performance_returns,
)
from app.services.portfolio.pnl_tracker import PortfolioPnLSnapshot
from app.services.risk.advanced_risk import _actual_account_returns, calculate_advanced_risk_metrics


def _summary() -> AccountSummary:
    return AccountSummary(
        account_id="TEST-001",
        net_liquidation=100_000.0,
        cash=10_000.0,
        buying_power=0.0,
        margin_requirement=0.0,
        excess_liquidity=0.0,
        total_unrealized_pnl=0.0,
        total_realized_pnl=0.0,
        base_currency="USD",
        data_timestamp=utc_now(),
    )


def _snapshot(day: date, nav: float, timestamp: str) -> PortfolioPnLSnapshot:
    return PortfolioPnLSnapshot(
        date=day.isoformat(),
        timestamp=timestamp,
        net_liquidation=nav,
        cash=0.0,
        buying_power=0.0,
        margin_requirement=0.0,
        daily_pnl=0.0,
        daily_pnl_percent=0.0,
        positions=[],
    )


def _transaction(action: str, day: date, amount: float) -> Transaction:
    return Transaction(
        account_id="TEST-001",
        symbol="CASH",
        trade_date=day,
        action=action,  # type: ignore[arg-type]
        quantity=1.0,
        price=amount,
        commission=0.0,
        currency="USD",
        amount=amount,
        source="ibkr_flex_query",
    )


def _position() -> Position:
    return Position(
        account_id="TEST-001",
        symbol="MSFT",
        company_name="Microsoft",
        asset_class="STK",
        quantity=10.0,
        avg_cost=100.0,
        market_price=110.0,
        market_value=1100.0,
        unrealized_pnl=100.0,
        realized_pnl=0.0,
        currency="USD",
        exchange="SMART",
        sector="Technology",
        industry="Software",
        portfolio_weight=1.1,
        stock_type="core",
        is_etf=False,
        is_speculative=False,
        updated_at=utc_now(),
    )


def test_complete_activity_ledger_can_have_zero_external_flows():
    start = date(2026, 1, 1)
    end = date(2026, 6, 30)
    coverage = build_ledger_coverage(
        "TEST-001",
        transactions=[],
        imported_sections=["executions", "flex_cash_ledger"],
        period_start=start,
        period_end=end,
    )
    assert coverage.status == "completed"
    assert coverage.has_external_cash_flows is False
    assert coverage.execution_only is False
    assert ledger_covers_period(coverage, start, end) is True


def test_execution_only_sync_never_claims_full_ledger_coverage():
    day = date(2026, 1, 2)
    buy = Transaction(
        account_id="TEST-001",
        symbol="MSFT",
        trade_date=day,
        action="buy",
        quantity=1.0,
        price=100.0,
        commission=0.0,
        currency="USD",
        source="ibkr_readonly",
    )
    coverage = build_ledger_coverage(
        "TEST-001",
        transactions=[buy],
        imported_sections=["executions"],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 6, 30),
    )
    assert coverage.execution_only is True
    assert coverage.status == "partial"
    assert ledger_covers_period(coverage, date(2026, 1, 1), date(2026, 6, 30)) is False


def test_xirr_does_not_double_count_opening_date_contribution():
    start = date(2026, 1, 1)
    end = date(2026, 12, 31)
    flows = build_xirr_cash_flows(
        [
            _transaction("deposit", start, 10_000.0),
            _transaction("deposit", start + timedelta(days=30), 5_000.0),
        ],
        opening_nav=100_000.0,
        opening_date=start,
        terminal_nav=120_000.0,
        terminal_date=end,
        period_start=start,
        period_end=end,
        base_currency="USD",
        fx_resolver=lambda _a, _b: 1.0,
    )
    assert (start, -100_000.0) in flows
    assert (start, -10_000.0) not in flows
    assert (start + timedelta(days=30), -5_000.0) in flows


def test_performance_keeps_latest_snapshot_per_day(monkeypatch):
    start = date(2026, 1, 1)
    end = date(2026, 2, 1)
    coverage = build_ledger_coverage(
        "TEST-001",
        transactions=[],
        imported_sections=["flex_cash_ledger"],
        period_start=start,
        period_end=end,
    )
    monkeypatch.setattr("app.services.portfolio.performance_returns.get_transactions", lambda _account: [])
    monkeypatch.setattr("app.services.portfolio.performance_returns.load_ledger_coverage", lambda _account: coverage)
    monkeypatch.setattr(
        "app.services.portfolio.benchmark_returns.align_benchmark_comparison",
        lambda *_args, **_kwargs: {"status": "missing"},
    )
    history = [
        _snapshot(start, 100.0, "2026-01-01T10:00:00Z"),
        _snapshot(start, 101.0, "2026-01-01T23:00:00Z"),
        _snapshot(end, 102.0, "2026-02-01T23:00:00Z"),
    ]
    result = calculate_performance_returns("TEST-001", history, "USD", lambda _a, _b: 1.0)
    assert result.observation_count == 2
    assert result.time_weighted_return == pytest.approx((102.0 / 101.0 - 1.0) * 100.0, abs=1e-4)


def test_benchmark_alignment_uses_prior_close_for_weekend(monkeypatch):
    from app.services.portfolio.benchmark_returns import align_benchmark_comparison

    friday = date(2026, 1, 2)
    saturday = date(2026, 1, 3)
    monkeypatch.setattr(
        "app.services.portfolio.benchmark_returns._fetch_total_return_series",
        lambda *_args, **_kwargs: ({friday.isoformat(): 100.0}, "test_total_return"),
    )
    result = align_benchmark_comparison(
        [_snapshot(friday, 100.0, "a"), _snapshot(saturday, 100.0, "b")],
        portfolio_twr_percent=0.0,
        benchmark_symbols=["SPY"],
    )
    assert result["spy_return_percent"] == 0.0
    assert result["spy_observations"] == 2


def test_actual_account_returns_remove_external_cash_flow(monkeypatch):
    start = date(2026, 1, 1)
    end = date(2026, 1, 2)
    deposit = _transaction("deposit", end, 50.0)
    coverage = build_ledger_coverage(
        "TEST-001",
        [deposit],
        imported_sections=["flex_cash_ledger"],
        period_start=start,
        period_end=end,
    )
    monkeypatch.setattr("app.services.portfolio.ledger_coverage.load_ledger_coverage", lambda _account: coverage)
    monkeypatch.setattr("app.services.portfolio.transaction_store.get_transactions", lambda _account: [deposit])
    monkeypatch.setattr("app.services.broker.ibkr_readonly.get_exchange_rate", lambda _a, _b: 1.0)
    returns, _, status = _actual_account_returns(
        _summary(),
        [_snapshot(start, 100.0, "a"), _snapshot(end, 150.0, "b")],
    )
    assert status == "sufficient"
    assert returns == [0.0]


def test_advanced_risk_withholds_historical_metrics_without_complete_ledger(monkeypatch):
    monkeypatch.setattr("app.services.portfolio.ledger_coverage.load_ledger_coverage", lambda _account: None)
    monkeypatch.setattr("app.services.broker.ibkr_readonly.get_exchange_rate", lambda _a, _b: 1.0)
    monkeypatch.setattr(
        "app.services.risk.advanced_risk._benchmark_returns_for_dates",
        lambda *_args, **_kwargs: ([], "missing"),
    )
    monkeypatch.setattr(
        "app.services.risk.history_reconstructor.reconstruct_portfolio_history",
        lambda *_args, **_kwargs: None,
    )
    history = [
        _snapshot(date(2026, 1, 1), 100_000.0, "a"),
        _snapshot(date(2026, 1, 2), 95_000.0, "b"),
        _snapshot(date(2026, 1, 3), 105_000.0, "c"),
    ]
    result = calculate_advanced_risk_metrics([_position()], _summary(), history)
    assert result.max_drawdown is None
    assert result.volatility is None
    assert result.sharpe_ratio is None
    assert result.data_quality["historical_metrics"] == "insufficient"
    assert result.data_quality["cash_flow_ledger"] == "missing"


def test_policy_drift_converts_position_values_to_base_currency(monkeypatch):
    from app.schemas.domain import InvestmentPolicyStatement
    from app.services.policy.engine import analyze_policy_drift

    position = _position().model_copy(
        update={
            "currency": "CAD",
            "market_value": 10_000.0,
            "portfolio_weight": 0.0,
        }
    )
    policy = InvestmentPolicyStatement(
        target_equity_percent=50.0,
        target_cash_percent=50.0,
        target_bond_percent=0.0,
        max_single_stock_weight=40.0,
        max_speculative_weight=10.0,
        max_sector_weight=50.0,
        max_options_exposure=3.0,
        minimum_cash=0.0,
        benchmark="SPY",
        rebalancing_drift_threshold=5.0,
    )
    result = analyze_policy_drift(
        [position],
        cash=5_000.0,
        total_val=10_000.0,
        policy=policy,
        base_currency="USD",
        fx_resolver=lambda _a, _b: 0.5,
    )
    assert result["drifts"]["equity"]["current"] == 50.0
    assert result["reporting_currency"] == "USD"


def test_rebalance_trade_values_and_quantities_are_fx_consistent(monkeypatch):
    from app.schemas.domain import InvestmentPolicyStatement, InvestorProfile
    from app.services.portfolio_construction.engine import generate_rebalance_proposal

    monkeypatch.setattr("app.services.broker.ibkr_readonly.get_exchange_rate", lambda _a, _b: 0.5)
    position = _position().model_copy(
        update={
            "currency": "CAD",
            "quantity": 100.0,
            "market_price": 100.0,
            "market_value": 10_000.0,
            "portfolio_weight": 0.0,
        }
    )
    summary = _summary().model_copy(update={"net_liquidation": 10_000.0, "cash": 0.0, "base_currency": "USD"})
    policy = InvestmentPolicyStatement(
        target_equity_percent=100.0,
        target_cash_percent=0.0,
        target_bond_percent=0.0,
        max_single_stock_weight=25.0,
        max_speculative_weight=10.0,
        max_sector_weight=100.0,
        max_options_exposure=3.0,
        minimum_cash=0.0,
        benchmark="SPY",
        rebalancing_drift_threshold=5.0,
    )
    profile = InvestorProfile(
        objective="Growth",
        time_horizon_years=10,
        risk_tolerance="High",
        risk_capacity="High",
        liquidity_needs=0.0,
        net_worth_range="100k-500k",
        tax_residency="Canada",
        account_type="Taxable",
        restrictions=[],
    )
    result = generate_rebalance_proposal([position], summary, policy, profile)
    sale = next(item for item in result.proposed_trades if item.symbol == "MSFT")
    # CAD 10,000 becomes USD 5,000; reducing to 25% of USD 10,000 sells USD 2,500.
    assert sale.proposed_trade_value == -2_500.0
    # Base-currency price is USD 50, so 50 shares are sold.
    assert sale.proposed_trade_qty == -50.0
