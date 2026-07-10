from __future__ import annotations

import math
from datetime import date

import pytest

from app.schemas.domain import Transaction
from app.services.market_data.fx_store import _lookup_rate
from app.services.portfolio.corporate_actions import parse_corporate_action
from app.services.portfolio.tax_lots import build_tax_lot_attribution
from app.services.risk.advanced_risk import _historical_metrics


def test_historical_var_uses_95th_percentile_loss_not_5th():
    returns = [-0.10, -0.08, -0.06, -0.05, -0.04, -0.03, -0.02, -0.01, 0.0, 0.01] * 3
    metrics = _historical_metrics(returns, returns, 0.0, 100_000.0)
    assert metrics["historical_var_95"] is not None
    assert metrics["historical_var_95"] == pytest.approx(10_000.0, rel=0.05)
    assert metrics["historical_es_95"] is not None
    assert metrics["historical_es_95"] >= metrics["historical_var_95"]


def test_fx_lookup_never_uses_future_observation():
    series = {"2024-01-10": 1.30, "2024-02-10": 1.35}
    assert _lookup_rate(series, date(2024, 1, 10)) == 1.30
    assert _lookup_rate(series, date(2024, 1, 20)) == 1.30
    assert _lookup_rate(series, date(2024, 1, 5)) is None


def test_canadian_tax_output_is_withheld():
    report = build_tax_lot_attribution(
        "MOCK-001",
        [],
        reporting_currency="CAD",
        tax_labeling_jurisdiction="CA",
    )
    assert report.data_quality["status"] == "unavailable"
    assert report.data_quality["tax_lot_method"] == "acb_withheld"


def test_unparsed_corporate_action_marks_tax_lots_incomplete():
    transactions = [
        Transaction(
            account_id="MOCK-001",
            symbol="SPY",
            trade_date=date(2024, 1, 1),
            action="buy",
            quantity=10,
            price=400,
            commission=0,
            currency="USD",
        ),
        Transaction(
            account_id="MOCK-001",
            symbol="SPY",
            trade_date=date(2024, 6, 1),
            action="corporate_action",
            quantity=0,
            price=0,
            commission=0,
            currency="USD",
            description="Merger consideration pending allocation",
        ),
    ]
    report = build_tax_lot_attribution("MOCK-001", transactions, reporting_currency="USD")
    assert report.data_quality["status"] == "incomplete"
    assert report.data_quality.get("corporate_actions") == "corporate_actions_partial"


def test_explicit_split_parses_ratio_only():
    txn = Transaction(
        account_id="MOCK-001",
        symbol="SPY",
        trade_date=date(2024, 6, 1),
        action="corporate_action",
        quantity=0,
        price=0,
        commission=0,
        currency="USD",
        description="Stock Split 2 for 1",
    )
    action = parse_corporate_action(txn)
    assert action is not None
    assert math.isclose(action.ratio, 2.0)


def test_guessed_reverse_split_is_not_parsed():
    txn = Transaction(
        account_id="MOCK-001",
        symbol="SPY",
        trade_date=date(2024, 6, 1),
        action="corporate_action",
        quantity=0,
        price=0,
        commission=0,
        currency="USD",
        description="Reverse split effective",
    )
    assert parse_corporate_action(txn) is None
