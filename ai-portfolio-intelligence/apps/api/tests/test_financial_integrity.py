from datetime import date, timedelta

import pytest

from app.schemas.domain import (
    AccountSummary,
    InvestmentPolicyStatement,
    InvestorProfile,
    Position,
    Transaction,
    utc_now,
)
from app.services.portfolio_construction.engine import generate_rebalance_proposal
from app.services.attribution.engine import calculate_brinson_attribution, calculate_performance_attribution
from app.services.broker.flex_query import FlexParseResult, _map_flex_action, _parse_flex_csv
from app.services.fundamentals.snapshot_store import get_point_in_time_fundamentals, seed_demo_fundamentals_records
from app.services.fundamentals.mock_provider import MockFundamentalProvider
from app.services.portfolio.benchmark_returns import align_benchmark_comparison
from app.services.portfolio.ledger_coverage import (
    build_ledger_coverage,
    external_cash_flow_amount,
    external_cash_flows_for_interval,
    ledger_covers_period,
)
from app.services.portfolio.performance_returns import (
    build_xirr_cash_flows,
    calculate_performance_returns,
)
from app.services.portfolio.pnl_tracker import PortfolioPnLSnapshot
from app.services.portfolio.tax_lots import build_tax_lot_attribution
from app.services.scoring.stock_score import score_stock


def _txn(action: str, trade_date: date, amount: float, source: str = "ibkr_flex_query") -> Transaction:
    return Transaction(
        account_id="MOCK-001",
        symbol="CASH",
        trade_date=trade_date,
        action=action,  # type: ignore[arg-type]
        quantity=1,
        price=amount,
        commission=0,
        currency="USD",
        amount=amount,
        source=source,
    )


def test_dividends_and_interest_are_not_external_flows():
    assert external_cash_flow_amount(_txn("dividend", date.today(), 50)) == 0.0
    assert external_cash_flow_amount(_txn("interest", date.today(), 12)) == 0.0
    assert external_cash_flow_amount(_txn("buy", date.today(), 1000)) == 0.0


def test_weekend_cash_flow_assigned_to_next_snapshot_interval():
    friday = date(2025, 1, 3)
    saturday = date(2025, 1, 4)
    monday = date(2025, 1, 6)
    flows = external_cash_flows_for_interval(
        [_txn("deposit", saturday, 1000)],
        friday,
        monday,
        "USD",
        lambda _a, _b: 1.0,
    )
    assert flows == 1000.0


def test_execution_only_ledger_marked_partial():
    coverage = build_ledger_coverage(
        "MOCK-001",
        [
            Transaction(
                account_id="MOCK-001",
                symbol="MSFT",
                trade_date=date.today(),
                action="buy",
                quantity=1,
                price=100,
                commission=0,
                currency="USD",
                source="ibkr_readonly",
            )
        ],
        imported_sections=["executions"],
        period_start=date.today() - timedelta(days=30),
        period_end=date.today(),
    )
    assert coverage.execution_only is True
    assert coverage.has_external_cash_flows is False
    assert coverage.status == "partial"


def test_opening_and_terminal_nav_included_in_xirr():
    period_start = date(2025, 1, 1)
    period_end = date(2025, 12, 31)
    flows = build_xirr_cash_flows(
        [_txn("deposit", date(2025, 6, 1), 5000)],
        opening_nav=100000,
        opening_date=period_start,
        terminal_nav=110000,
        terminal_date=period_end,
        period_start=period_start,
        period_end=period_end,
        base_currency="USD",
        fx_resolver=lambda _a, _b: 1.0,
    )
    assert flows[0] == (period_start, -100000)
    assert flows[-1] == (period_end, 110000)
    assert any(amount == -5000 for _, amount in flows)


def test_twr_withheld_without_full_external_ledger_coverage(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.portfolio.transaction_store.DATA_DIR", str(tmp_path))
    history = [
        PortfolioPnLSnapshot(
            date=(date.today() - timedelta(days=30)).isoformat(),
            timestamp="t1",
            net_liquidation=100000,
            cash=10000,
            buying_power=0,
            margin_requirement=0,
            daily_pnl=0,
            daily_pnl_percent=0,
            positions=[],
        ),
        PortfolioPnLSnapshot(
            date=date.today().isoformat(),
            timestamp="t2",
            net_liquidation=105000,
            cash=10000,
            buying_power=0,
            margin_requirement=0,
            daily_pnl=5000,
            daily_pnl_percent=5,
            positions=[],
        ),
    ]
    returns = calculate_performance_returns("MOCK-001", history, "USD", lambda _a, _b: 1.0, allow_mock=True)
    assert returns.time_weighted_return is None
    assert returns.xirr is None
    assert returns.data_quality["cash_flow_adjustment"] == "missing"


def test_no_mock_benchmark_source_in_live_mode():
    history = [
        PortfolioPnLSnapshot(
            date=(date.today() - timedelta(days=10)).isoformat(),
            timestamp="t1",
            net_liquidation=100000,
            cash=10000,
            buying_power=0,
            margin_requirement=0,
            daily_pnl=0,
            daily_pnl_percent=0,
            positions=[],
        ),
        PortfolioPnLSnapshot(
            date=date.today().isoformat(),
            timestamp="t2",
            net_liquidation=101000,
            cash=10000,
            buying_power=0,
            margin_requirement=0,
            daily_pnl=1000,
            daily_pnl_percent=1,
            positions=[],
        ),
    ]
    comparison = align_benchmark_comparison(history, portfolio_twr_percent=1.0, allow_mock=False)
    assert comparison.get("spy_source") != "mock_market_data"


def test_excess_return_withheld_without_valid_portfolio_twr():
    history = [
        PortfolioPnLSnapshot(
            date=(date.today() - timedelta(days=5)).isoformat(),
            timestamp="t1",
            net_liquidation=100000,
            cash=10000,
            buying_power=0,
            margin_requirement=0,
            daily_pnl=0,
            daily_pnl_percent=0,
            positions=[],
        ),
        PortfolioPnLSnapshot(
            date=date.today().isoformat(),
            timestamp="t2",
            net_liquidation=101000,
            cash=10000,
            buying_power=0,
            margin_requirement=0,
            daily_pnl=1000,
            daily_pnl_percent=1,
            positions=[],
        ),
    ]
    comparison = align_benchmark_comparison(history, portfolio_twr_percent=None, allow_mock=True)
    assert comparison["spy_excess_return_percent"] is None


def test_unknown_flex_activity_rejected():
    row = {"ActivityType": "Mystery Event", "Description": "Something new", "Date": "2025-01-01"}
    assert _map_flex_action(row) is None
    result = _parse_flex_csv("U123", "ActivityType,Description,Date,Amount,CurrencyPrimary,Quantity,Price,Commission\nMystery,Something,2025-01-01,10,USD,1,10,0\n")
    assert result.rejected_row_count == 1
    assert not result.transactions


def test_synthetic_pit_data_prohibited_in_live_mode(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.fundamentals.snapshot_store.DATA_DIR", str(tmp_path))
    base = MockFundamentalProvider(allow_mock=True).get_fundamentals("MSFT")
    seed_demo_fundamentals_records("MSFT", base)
    assert get_point_in_time_fundamentals("MSFT", date.today(), allow_synthetic_demo=False) is None


def test_invalid_brinson_output_withheld():
    alloc, sel, inter, active, by_sector, _ = calculate_brinson_attribution(
        [],
        "USD",
        lambda _a, _b: 1.0,
        allow_mock=True,
        portfolio_sector_returns=None,
    )
    assert alloc is None and sel is None and inter is None and active is None and by_sector == {}


def test_unmatched_tax_lot_sells_marked_incomplete():
    report = build_tax_lot_attribution(
        "MOCK-001",
        [
            Transaction(
                account_id="MOCK-001",
                symbol="AAPL",
                trade_date=date(2025, 1, 1),
                action="sell",
                quantity=10,
                price=150,
                commission=0,
                currency="USD",
            )
        ],
        reporting_currency="USD",
        tax_labeling_jurisdiction="CA",
    )
    assert report.data_quality["status"] == "incomplete"
    assert report.unmatched_sell_quantity > 0
    assert report.realized_by_symbol[0].short_term_gain_loss is None


def test_live_invalid_symbol_score_withheld():
    position = Position(
        account_id="U1234567",
        symbol="INVALIDTICKER",
        company_name="Invalid",
        asset_class="STK",
        quantity=100,
        avg_cost=150.0,
        market_price=160.0,
        market_value=16000.0,
        unrealized_pnl=1000.0,
        currency="USD",
        exchange="NASDAQ",
        sector="Technology",
        industry="Software",
        portfolio_weight=5.0,
        stock_type="core",
        updated_at=utc_now(),
    )
    score = score_stock(position, allow_mock=False)
    assert score.final_score is None
    assert "60%" in score.explanation


def test_rebalancing_proposes_aapl_and_ionq_sells():
    profile = InvestorProfile(
        objective="Growth",
        time_horizon_years=10,
        risk_tolerance="High",
        risk_capacity="High",
        liquidity_needs=5000.0,
        net_worth_range="100k-500k",
        tax_residency="Canada",
        account_type="Taxable",
        restrictions=[],
    )
    policy = InvestmentPolicyStatement(
        target_equity_percent=80.0,
        target_cash_percent=20.0,
        target_bond_percent=0.0,
        max_single_stock_weight=10.0,
        max_speculative_weight=5.0,
        minimum_cash=10000.0,
        benchmark="SPY",
        rebalancing_drift_threshold=5.0,
    )
    positions = [
        Position(
            account_id="TEST-001",
            symbol="AAPL",
            company_name="Apple Inc.",
            asset_class="STK",
            quantity=136,
            avg_cost=100.0,
            market_price=110.0,
            market_value=14960.0,
            unrealized_pnl=1360.0,
            currency="USD",
            exchange="SMART",
            sector="Technology",
            industry="Hardware",
            portfolio_weight=15.0,
            stock_type="core",
            is_speculative=False,
            updated_at=utc_now(),
        ),
        Position(
            account_id="TEST-001",
            symbol="IONQ",
            company_name="IonQ Inc.",
            asset_class="STK",
            quantity=73,
            avg_cost=100.0,
            market_price=110.0,
            market_value=8030.0,
            unrealized_pnl=730.0,
            currency="USD",
            exchange="SMART",
            sector="Technology",
            industry="Quantum",
            portfolio_weight=8.0,
            stock_type="speculative_growth",
            is_speculative=True,
            updated_at=utc_now(),
        ),
    ]
    summary = AccountSummary(
        account_id="TEST-001",
        net_liquidation=100000.0,
        cash=5000.0,
        buying_power=0.0,
        margin_requirement=0.0,
        excess_liquidity=0.0,
        total_unrealized_pnl=0.0,
        total_realized_pnl=0.0,
        base_currency="USD",
        data_timestamp=utc_now(),
    )
    proposal = generate_rebalance_proposal(positions, summary, policy, profile)
    sells = [trade for trade in proposal.proposed_trades if trade.action == "Sell"]
    assert any(trade.symbol == "AAPL" for trade in sells)
    assert any(trade.symbol == "IONQ" for trade in sells)


def test_ledger_covers_period_requires_external_rows():
    coverage = build_ledger_coverage(
        "MOCK-001",
        [_txn("deposit", date.today() - timedelta(days=400), 1000)],
        imported_sections=["flex_cash_ledger"],
        period_start=date.today() - timedelta(days=30),
        period_end=date.today(),
    )
    assert ledger_covers_period(coverage, date.today() - timedelta(days=30), date.today()) is False
