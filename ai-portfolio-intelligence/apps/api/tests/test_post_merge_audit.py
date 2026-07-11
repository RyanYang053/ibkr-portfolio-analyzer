from __future__ import annotations

import math
from datetime import date

import pytest

from app.schemas.domain import Transaction
from app.services.fundamentals.snapshot_store import save_snapshot_record
from app.services.market_data.fx_store import _lookup_rate
from app.services.portfolio.corporate_actions import parse_corporate_action
from app.services.portfolio.tax_lots import build_tax_lot_attribution
from app.services.risk.advanced_risk import _historical_metrics


def test_historical_var_uses_95th_percentile_loss_not_5th():
    returns = [-0.10, -0.08, -0.06, -0.05, -0.04, -0.03, -0.02, -0.01, 0.0, 0.01] * 10
    metrics = _historical_metrics(returns, returns, 0.0, 100_000.0)
    assert metrics["historical_var_95"] is not None
    assert metrics["historical_var_95"] == pytest.approx(10_000.0, rel=0.05)
    assert metrics["historical_es_95"] is not None
    assert metrics["historical_es_95"] >= metrics["historical_var_95"]


def test_fx_lookup_never_uses_future_observation():
    series = {"2024-01-10": 1.30, "2024-02-10": 1.35}
    assert _lookup_rate(series, date(2024, 1, 10)) == 1.30
    assert _lookup_rate(series, date(2024, 1, 16)) == 1.30
    assert _lookup_rate(series, date(2024, 1, 5)) is None
    assert _lookup_rate(series, date(2024, 1, 20)) is None


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


def test_explicit_reverse_split_ratio_is_not_inverted():
    txn = Transaction(
        account_id="MOCK-001",
        symbol="SPY",
        trade_date=date(2024, 6, 1),
        action="corporate_action",
        quantity=0,
        price=0,
        commission=0,
        currency="USD",
        description="Reverse split 1 for 10",
    )
    action = parse_corporate_action(txn)
    assert action is not None
    assert math.isclose(action.ratio, 0.1)


def test_explicit_forward_split_ratio():
    txn = Transaction(
        account_id="MOCK-001",
        symbol="SPY",
        trade_date=date(2024, 6, 1),
        action="corporate_action",
        quantity=0,
        price=0,
        commission=0,
        currency="USD",
        description="Stock split 10 for 1",
    )
    action = parse_corporate_action(txn)
    assert action is not None
    assert math.isclose(action.ratio, 10.0)


def test_pre_period_sell_consumes_lots_before_in_period_match():
    transactions = [
        Transaction(
            account_id="MOCK-001",
            symbol="MSFT",
            trade_date=date(2024, 1, 1),
            action="buy",
            quantity=100,
            price=10,
            commission=0,
            currency="USD",
        ),
        Transaction(
            account_id="MOCK-001",
            symbol="MSFT",
            trade_date=date(2024, 6, 1),
            action="sell",
            quantity=50,
            price=12,
            commission=0,
            currency="USD",
        ),
        Transaction(
            account_id="MOCK-001",
            symbol="MSFT",
            trade_date=date(2025, 1, 15),
            action="sell",
            quantity=30,
            price=15,
            commission=0,
            currency="USD",
        ),
    ]
    report = build_tax_lot_attribution(
        "MOCK-001",
        transactions,
        reporting_currency="USD",
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        tax_labeling_jurisdiction="US",
    )
    assert report.data_quality["status"] == "lot_matching_complete"
    assert report.total_realized_gain_loss == pytest.approx(150.0)
    assert len(report.realized_by_symbol) == 1
    assert report.realized_by_symbol[0].unmatched_sell_quantity == 0.0
    open_qty = sum(lot.quantity for lot in report.lots_open if lot.symbol == "MSFT")
    assert open_qty == pytest.approx(20.0)


def test_fetch_flex_cash_ledger_calls_defined_transport(monkeypatch):
    from app.services.broker import flex_query

    monkeypatch.setattr(flex_query.settings, "ibkr_flex_token", "token")
    monkeypatch.setattr(flex_query.settings, "ibkr_flex_activity_query_id", "qid")
    monkeypatch.setattr(
        flex_query,
        "_request_flex_statement",
        lambda token, query: (
            "AccountId,Date,ActivityType,Amount,Currency\n"
            "U1,2026-01-02,Deposit,1000,USD\n"
        ),
    )

    result = flex_query.fetch_flex_cash_ledger("U1")
    assert len(result.transactions) == 1
    assert result.report_period_start is None
    assert result.report_period_end is None


def test_flex_csv_does_not_infer_statement_period_from_transaction_dates():
    from app.services.broker.flex_query import _parse_flex_csv

    payload = (
        "AccountId,Date,ActivityType,Amount,Currency,Symbol,Quantity,Price\n"
        "U1,2026-06-15,Deposit,1000,USD,CASH,1,1000\n"
    )
    result = _parse_flex_csv("U1", payload)
    assert len(result.transactions) == 1
    assert result.report_period_start is None
    assert result.report_period_end is None


def test_flex_xml_zero_row_statement_preserves_explicit_period():
    from app.services.broker.flex_query import _parse_flex_xml

    payload = """<?xml version="1.0"?>
    <FlexQueryResponse>
      <FlexStatements count="1">
        <FlexStatement accountId="U1" fromDate="20260101" toDate="20261231"
          whenGenerated="20260701;120000"/>
      </FlexStatements>
    </FlexQueryResponse>"""
    result = _parse_flex_xml("U1", payload, query_id="qid")
    assert result.transactions == []
    assert result.report_period_start == date(2026, 1, 1)
    assert result.report_period_end == date(2026, 12, 31)
    assert result.account_id == "U1"


def test_request_flex_statement_polls_until_statement_ready(monkeypatch):
    from app.services.broker import flex_query

    send_response = type(
        "Resp",
        (),
        {
            "text": (
                "<FlexStatementResponse>"
                "<Status>Success</Status>"
                "<ReferenceCode>REF123</ReferenceCode>"
                "</FlexStatementResponse>"
            ),
            "raise_for_status": lambda self: None,
        },
    )()
    processing_response = type(
        "Resp",
        (),
        {
            "text": "<FlexStatementResponse><Status>Warn</Status></FlexStatementResponse>",
            "raise_for_status": lambda self: None,
        },
    )()
    completed_response = type(
        "Resp",
        (),
        {
            "text": (
                "<FlexQueryResponse><FlexStatements>"
                '<FlexStatement accountId="U1" fromDate="20260101" toDate="20260131"/>'
                "</FlexStatements></FlexQueryResponse>"
            ),
            "raise_for_status": lambda self: None,
        },
    )()

    poll_calls = {"count": 0}

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, params=None):
            if url == flex_query.FLEX_SEND_URL:
                return send_response
            poll_calls["count"] += 1
            if poll_calls["count"] == 1:
                return processing_response
            return completed_response

    monkeypatch.setattr(flex_query.httpx, "Client", FakeClient)
    monkeypatch.setattr(flex_query.time, "sleep", lambda _seconds: None)

    payload = flex_query._request_flex_statement("token", "qid", timeout_seconds=5.0)
    assert "FlexStatement" in payload
    assert poll_calls["count"] >= 2


def test_sharpe_uses_daily_excess_returns():
    from app.services.risk.advanced_risk import _historical_metrics

    returns = [0.01, -0.005, 0.008, -0.003, 0.004, -0.002] * 5
    spy_returns = [0.0005] * 30
    metrics = _historical_metrics(returns, spy_returns, 0.02, 100_000.0)
    assert metrics["sharpe_ratio"] is not None
    assert metrics["sortino_ratio"] is not None
    assert metrics["information_ratio"] is not None


def test_historical_var_requires_100_observations():
    from app.services.risk.advanced_risk import _historical_metrics

    returns = [0.001, -0.002, 0.003] * 25  # 75 observations
    metrics = _historical_metrics(returns, returns, 0.0, 100_000.0)
    assert metrics["historical_var_95"] is None
    assert metrics["historical_es_95"] is None


def test_current_fundamental_record_does_not_overwrite_pit_record(tmp_path, monkeypatch):
    from datetime import datetime, timezone

    from app.schemas.domain import FundamentalSnapshot, FundamentalSnapshotRecord
    from app.services.fundamentals import snapshot_store

    monkeypatch.setattr(snapshot_store, "DATA_DIR", str(tmp_path))
    filing_day = date(2024, 3, 15)
    pit_snapshot = FundamentalSnapshot(
        symbol="MSFT",
        period="TTM",
        report_date=filing_day,
        revenue_growth_yoy=0.1,
        gross_margin=0.4,
        operating_margin=0.2,
        free_cash_flow=1_000.0,
        cash=10_000.0,
        total_debt=5_000.0,
        pe_forward=None,
        ev_sales=None,
        fcf_yield=None,
        source="pit_source",
    )
    save_snapshot_record(
        FundamentalSnapshotRecord(
            symbol="MSFT",
            as_of_date=filing_day,
            snapshot=pit_snapshot,
            point_in_time=True,
            source="pit_source",
            filing_date=filing_day,
            ingested_at=datetime(2024, 3, 16, tzinfo=timezone.utc),
        )
    )
    current_snapshot = pit_snapshot.model_copy(update={"source": "live_yahoo_finance", "revenue_growth_yoy": 0.2})
    save_snapshot_record(
        FundamentalSnapshotRecord(
            symbol="MSFT",
            as_of_date=date(2026, 7, 10),
            snapshot=current_snapshot,
            point_in_time=False,
            source="live_yahoo_finance",
            filing_date=filing_day,
            ingested_at=datetime(2026, 7, 10, tzinfo=timezone.utc),
        )
    )
    records = snapshot_store.list_snapshot_records("MSFT")
    assert len(records) == 1
    assert records[0].point_in_time is True
    assert records[0].snapshot.revenue_growth_yoy == 0.1


def test_close_only_bars_still_compute_rsi_when_some_rows_missing_hlc():
    from app.services.technicals.indicators import calculate_technical_indicators_from_bars

    bars = []
    for index in range(260):
        day = date(2024, 1, 1).toordinal() + index
        bar = {
            "date": date.fromordinal(day).isoformat(),
            "close": 100.0 + index * 0.1,
        }
        if index % 5 != 0:
            bar["high"] = float(bar["close"]) + 1.0
            bar["low"] = float(bar["close"]) - 1.0
        bars.append(bar)
    indicators = calculate_technical_indicators_from_bars("MSFT", bars)
    assert indicators.rsi_14 is not None
    assert indicators.date.isoformat() == bars[-1]["date"]


def test_calibration_observation_schema_uses_benchmark_relative_excess():
    from app.services.scoring.calibration import run_score_calibration

    observations = [
        {
            "symbol": "MSFT",
            "model_name": "universal",
            "model_version": "2026.07.1",
            "feature_snapshot_hash": "hash1",
            "score": 80.0,
            "observed_on": "2024-01-01",
            "matured_on": "2024-04-01",
            "forward_total_return": 0.10,
            "benchmark_total_return": 0.04,
            "forward_excess_return": 0.06,
            "input_sources": ["live_yahoo_finance"],
            "synthetic_demo": False,
        }
    ]
    report = run_score_calibration(observations, model_name="universal")
    assert report.data_quality["return_basis"] == "benchmark_relative_excess"
    assert report.data_quality["status"] == "insufficient"
