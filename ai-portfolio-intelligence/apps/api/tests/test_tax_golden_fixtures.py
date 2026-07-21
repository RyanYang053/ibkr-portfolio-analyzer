from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.schemas.domain import Transaction
from app.services.tax.canadian_acb import build_canadian_acb_report
from app.services.tax.us_tax_lots import build_us_tax_lot_report

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "tax"


def _txn(row: dict) -> Transaction:
    return Transaction(
        source="golden",
        account_id=row["account_id"],
        symbol=row["symbol"],
        trade_date=date.fromisoformat(row["trade_date"]),
        action=row["action"],
        quantity=float(row["quantity"]),
        price=float(row["price"]),
        commission=float(row.get("commission") or 0),
        currency=row.get("currency") or "USD",
    )


@pytest.mark.golden
def test_us_fifo_wash_golden_fixture():
    payload = json.loads((FIXTURE_DIR / "us_fifo_wash.json").read_text(encoding="utf-8"))
    txs = [_txn(row) for row in payload["transactions"]]
    report = build_us_tax_lot_report(payload["transactions"][0]["account_id"], txs)
    expected = payload["expected"]
    tol = float(expected.get("tol_abs", 0.01))
    assert report.total_tax_realized_gain_loss == pytest.approx(expected["realized_gain_loss"], abs=tol)
    assert report.realized_lots[0].wash_sale_disallowed_loss == pytest.approx(
        expected["wash_sale_disallowed_loss"], abs=tol
    )
    assert report.open_lots[0].cost_basis_per_share == pytest.approx(
        expected["replacement_cost_basis_per_share"], abs=tol
    )
    assert report.data_quality.get("wash_sales_fully_adjusted") == "true"


@pytest.mark.golden
def test_ca_acb_basic_golden_fixture():
    payload = json.loads((FIXTURE_DIR / "ca_acb_basic.json").read_text(encoding="utf-8"))
    txs = [_txn(row) for row in payload["transactions"]]
    report = build_canadian_acb_report(payload["transactions"][0]["account_id"], txs)
    expected = payload["expected"]
    tol = float(expected.get("tol_abs", 0.01))
    assert report.total_tax_realized_gain_loss == pytest.approx(expected["realized_gain_loss"], abs=tol)
    assert report.open_lots[0].quantity == pytest.approx(expected["open_quantity"], abs=tol)
    assert report.open_lots[0].cost_basis_per_share == pytest.approx(
        expected["open_acb_per_share"], abs=tol
    )
