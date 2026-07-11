from __future__ import annotations

from datetime import date

from app.schemas.domain import Transaction
from app.services.portfolio.tax_lots import build_tax_lot_attribution
from app.services.tax.canadian_acb import build_canadian_acb_report, superficial_loss_blocked_symbols
from app.services.tax.models import TaxLotMethod
from app.services.tax.us_tax_lots import build_us_tax_lot_report


def _txn(**kwargs) -> Transaction:
    return Transaction(source="test", **kwargs)


def test_canadian_acb_pooled_realized_gain():
    transactions = [
        _txn(
            account_id="MOCK-001",
            symbol="RY",
            trade_date=date(2024, 1, 1),
            action="buy",
            quantity=100,
            price=100,
            commission=0,
            currency="CAD",
        ),
        _txn(
            account_id="MOCK-001",
            symbol="RY",
            trade_date=date(2025, 1, 1),
            action="sell",
            quantity=50,
            price=120,
            commission=0,
            currency="CAD",
        ),
    ]
    report = build_canadian_acb_report("MOCK-001", transactions)
    assert report.total_tax_realized_gain_loss == 1000.0
    assert report.method == TaxLotMethod.ACB


def test_us_tax_lots_fifo_short_and_long_term():
    transactions = [
        _txn(
            account_id="MOCK-001",
            symbol="AAPL",
            trade_date=date(2023, 1, 1),
            action="buy",
            quantity=10,
            price=100,
            commission=0,
            currency="USD",
        ),
        _txn(
            account_id="MOCK-001",
            symbol="AAPL",
            trade_date=date(2025, 2, 1),
            action="sell",
            quantity=10,
            price=150,
            commission=0,
            currency="USD",
        ),
    ]
    report = build_us_tax_lot_report("MOCK-001", transactions)
    assert report.total_tax_realized_gain_loss == 500.0
    assert report.total_long_term == 500.0


def test_build_tax_lot_attribution_routes_jurisdiction():
    ca = build_tax_lot_attribution("MOCK-001", [], reporting_currency="CAD", tax_labeling_jurisdiction="CA")
    assert ca.jurisdiction == "CA"
    assert ca.total_realized_gain_loss is None

    us = build_tax_lot_attribution(
        "MOCK-001",
        [
            _txn(
                account_id="MOCK-001",
                symbol="AAPL",
                trade_date=date(2024, 1, 1),
                action="buy",
                quantity=1,
                price=100,
                commission=0,
                currency="USD",
            ),
            _txn(
                account_id="MOCK-001",
                symbol="AAPL",
                trade_date=date(2025, 1, 1),
                action="sell",
                quantity=1,
                price=120,
                commission=0,
                currency="USD",
            ),
        ],
        tax_labeling_jurisdiction="US",
    )
    assert us.jurisdiction == "US"
    assert us.total_realized_gain_loss == 20.0


def test_canadian_superficial_loss_adds_to_acb_on_repurchase():
    transactions = [
        _txn(
            account_id="MOCK-001",
            symbol="RY",
            trade_date=date(2024, 1, 1),
            action="buy",
            quantity=100,
            price=100,
            commission=0,
            currency="CAD",
        ),
        _txn(
            account_id="MOCK-001",
            symbol="RY",
            trade_date=date(2024, 6, 1),
            action="sell",
            quantity=100,
            price=90,
            commission=0,
            currency="CAD",
        ),
        _txn(
            account_id="MOCK-001",
            symbol="RY",
            trade_date=date(2024, 6, 15),
            action="buy",
            quantity=100,
            price=92,
            commission=0,
            currency="CAD",
        ),
    ]
    report = build_canadian_acb_report("MOCK-001", transactions)
    assert report.data_quality["superficial_loss_adjustments"] == "1"
    assert "RY" in superficial_loss_blocked_symbols(report)
    assert report.open_lots[0].cost_basis_per_share > 92.0


def test_canadian_return_of_capital_reduces_acb():
    transactions = [
        _txn(
            account_id="MOCK-001",
            symbol="ENB",
            trade_date=date(2024, 1, 1),
            action="buy",
            quantity=100,
            price=50,
            commission=0,
            currency="CAD",
        ),
        _txn(
            account_id="MOCK-001",
            symbol="ENB",
            trade_date=date(2024, 6, 1),
            action="distribution",
            quantity=0,
            price=0,
            amount=500,
            commission=0,
            currency="CAD",
            description="Return of capital distribution",
        ),
    ]
    report = build_canadian_acb_report("MOCK-001", transactions)
    assert report.data_quality["return_of_capital_adjustments"] == "1"
    assert report.open_lots[0].cost_basis_per_share == 45.0
