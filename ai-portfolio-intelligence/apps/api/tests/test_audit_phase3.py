from datetime import date, timedelta

import pytest

from app.schemas.domain import Transaction
from app.services.broker.flex_query import _map_flex_action, _parse_flex_csv, mock_flex_transactions
from app.services.fundamentals.snapshot_store import get_point_in_time_fundamentals, seed_demo_fundamentals_records
from app.services.fundamentals.mock_provider import MockFundamentalProvider
from app.services.portfolio.benchmark_returns import align_benchmark_comparison
from app.services.portfolio.pnl_tracker import PortfolioPnLSnapshot
from app.services.portfolio.tax_lots import build_tax_lot_attribution


def test_flex_csv_parses_deposits_and_dividends():
    csv_payload = """ActivityType,Date,Symbol,Description,Amount,CurrencyPrimary,Quantity,Price,Commission
Deposits,2025-01-15,CASH,Electronic Fund Transfer Deposit,25000,USD,1,25000,0
Dividends,2025-03-01,MSFT,Dividend Payment,37.35,USD,45,0.83,0
"""
    result = _parse_flex_csv("U123", csv_payload)
    assert len(result.transactions) == 2
    assert result.transactions[0].action == "deposit"
    assert result.transactions[1].action == "dividend"


def test_flex_action_mapping():
    assert _map_flex_action({"Description": "Wire Deposit", "ActivityType": "Deposits"}) == "deposit"
    assert _map_flex_action({"Description": "Withdrawal to bank", "ActivityType": "Withdrawals"}) == "withdrawal"
    assert _map_flex_action({"Description": "Stock Split", "ActivityType": "Corporate Actions"}) == "corporate_action"


def test_mock_flex_transactions_include_cash_events():
    rows = mock_flex_transactions("MOCK-001")
    actions = {row.action for row in rows}
    assert "deposit" in actions
    assert "dividend" in actions


def test_benchmark_alignment_uses_portfolio_dates():
    history = [
        PortfolioPnLSnapshot(
            date=(date.today() - timedelta(days=30)).isoformat(),
            timestamp="t1",
            net_liquidation=100000,
            cash=10000,
            buying_power=50000,
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
            buying_power=50000,
            margin_requirement=0,
            daily_pnl=5000,
            daily_pnl_percent=5,
            positions=[],
        ),
    ]
    comparison = align_benchmark_comparison(history, portfolio_twr_percent=5.0, allow_mock=True)
    assert comparison.get("aligned_observations") == 2
    assert comparison.get("portfolio_twr_percent") == 5.0


def test_point_in_time_fundamentals_store(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.fundamentals.snapshot_store.DATA_DIR", str(tmp_path))
    base = MockFundamentalProvider(allow_mock=True).get_fundamentals("MSFT")
    seed_demo_fundamentals_records("MSFT", base)
    snapshot = get_point_in_time_fundamentals("MSFT", date.today(), allow_synthetic_demo=True)
    assert snapshot is not None
    assert snapshot.symbol == "MSFT"


def test_fifo_tax_lot_realized_attribution():
    transactions = [
        Transaction(
            account_id="MOCK-001",
            symbol="MSFT",
            trade_date=date(2024, 1, 1),
            action="buy",
            quantity=10,
            price=100,
            commission=0,
            currency="USD",
        ),
        Transaction(
            account_id="MOCK-001",
            symbol="MSFT",
            trade_date=date(2025, 6, 1),
            action="sell",
            quantity=4,
            price=130,
            commission=0,
            currency="USD",
        ),
    ]
    report = build_tax_lot_attribution("MOCK-001", transactions)
    assert report.total_realized_gain_loss == 120.0
    assert len(report.lots_open) == 1
    assert report.lots_open[0].quantity == 6
