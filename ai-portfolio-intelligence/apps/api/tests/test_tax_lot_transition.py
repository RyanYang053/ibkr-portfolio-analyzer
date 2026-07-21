"""Tax lot transition + optimizer coverage (registry validation fixture companion)."""

from __future__ import annotations

from datetime import date

import pytest

from app.schemas.domain import Transaction
from app.services.methodology_registry import DEFAULT_METHODOLOGIES
from app.services.tax.lot_optimizer import OpenLotView, optimize_tax_aware_sales, select_lots_for_sale
from app.services.tax.models import TaxLotMethod
from app.services.tax.tax_evidence import TaxOutputStatus, evaluate_tax_export_readiness
from app.services.tax.us_tax_lots import build_us_tax_lot_report


def _txn(**kwargs) -> Transaction:
    return Transaction(source="test", **kwargs)


def test_tax_lot_methodology_registry_points_at_fixture():
    record = next(item for item in DEFAULT_METHODOLOGIES if item.methodology_id == "tax_lot_methodology")
    assert record.approval_status == "approved_for_personal_use"
    assert record.version == "1.0.0"
    assert record.independent_validation_fixture == "tests/fixtures/tax/us_fifo_wash.json"


def test_select_lots_fifo_lifo_hifo():
    lots = [
        OpenLotView("AAPL", 10, 100, date(2020, 1, 1), lot_id="a"),
        OpenLotView("AAPL", 10, 150, date(2021, 1, 1), lot_id="b"),
        OpenLotView("AAPL", 10, 200, date(2022, 1, 1), lot_id="c"),
    ]
    fifo = select_lots_for_sale(lots, 15, method="fifo", mark_price=180)
    assert fifo[0].lot_id == "a"
    lifo = select_lots_for_sale(lots, 15, method="lifo", mark_price=180)
    assert lifo[0].lot_id == "c"
    hifo = select_lots_for_sale(lots, 15, method="hifo", mark_price=180)
    assert hifo[0].cost_basis_per_share == 200


def test_optimize_tax_aware_sales_never_orders():
    plan = optimize_tax_aware_sales(
        [
            {
                "symbol": "AAPL",
                "mark_price": 180,
                "lots": [
                    {"quantity": 10, "cost_basis_per_share": 100, "acquired_date": "2020-01-01"},
                    {"quantity": 10, "cost_basis_per_share": 200, "acquired_date": "2021-01-01"},
                ],
            }
        ],
        target_weights={"AAPL": 10},
        current_weights={"AAPL": 40},
        portfolio_value=10_000,
        method="hifo",
    )
    assert plan["order_generated"] is False
    assert plan["orders"] == []
    assert plan["lot_picks"]


def test_us_wash_sale_defers_loss_into_replacement_basis():
    transactions = [
        _txn(
            account_id="T1",
            symbol="MSFT",
            trade_date=date(2024, 1, 1),
            action="buy",
            quantity=50,
            price=100,
            commission=0,
            currency="USD",
        ),
        _txn(
            account_id="T1",
            symbol="MSFT",
            trade_date=date(2024, 6, 1),
            action="sell",
            quantity=50,
            price=80,
            commission=0,
            currency="USD",
        ),
        _txn(
            account_id="T1",
            symbol="MSFT",
            trade_date=date(2024, 6, 10),
            action="buy",
            quantity=50,
            price=85,
            commission=0,
            currency="USD",
        ),
    ]
    report = build_us_tax_lot_report("T1", transactions, lot_method=TaxLotMethod.FIFO)
    assert report.total_tax_realized_gain_loss == pytest.approx(0.0, abs=0.01)
    assert report.realized_lots[0].wash_sale_disallowed_loss == pytest.approx(1000.0, abs=0.01)
    assert report.open_lots[0].cost_basis_per_share == pytest.approx(105.0, abs=0.01)


def test_filing_ready_when_reconciled_and_approved():
    readiness = evaluate_tax_export_readiness(
        tax_year=2024,
        transaction_count=10,
        lots_reconciled=True,
        transactions_reconciled=True,
        corporate_actions_reviewed=True,
        wash_sales_fully_adjusted=True,
        methodology_approved_for_personal_use=True,
    )
    assert readiness.status == TaxOutputStatus.RECONCILED_ESTIMATE
    assert readiness.filing_ready is True
    assert readiness.filing_worksheet_ready is True
