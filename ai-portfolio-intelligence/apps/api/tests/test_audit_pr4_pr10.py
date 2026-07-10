from __future__ import annotations

from datetime import date

import pytest

from app.schemas.domain import Position, Transaction, utc_now
from app.services.analytics.calculation_run import create_calculation_run, load_calculation_run
from app.services.portfolio.ledger_coverage import TransactionLedgerCoverage, save_ledger_coverage
from app.services.portfolio.performance_returns import (
    _modified_dietz_interval_return,
    calculate_time_weighted_return,
)
from app.services.portfolio.pnl_decomposition import calculate_pnl_decomposition
from app.services.portfolio.pnl_tracker import PortfolioPnLSnapshot, PositionPnL
from app.services.portfolio.transaction_store import save_transactions
from app.services.risk.factor_model import _matrix_ols
from app.services.scoring.stock_score import score_stock


def _position(symbol: str = "AAPL") -> Position:
    return Position(
        account_id="TEST-001",
        symbol=symbol,
        company_name=symbol,
        asset_class="STK",
        quantity=10,
        avg_cost=100,
        market_price=110,
        market_value=1100,
        unrealized_pnl=100,
        currency="USD",
        exchange="NASDAQ",
        sector="Technology",
        industry="Software",
        portfolio_weight=5,
        stock_type="mega_cap_quality",
        updated_at=utc_now(),
    )


def _history() -> list[PortfolioPnLSnapshot]:
    return [
        PortfolioPnLSnapshot(
            date="2026-01-01",
            timestamp="2026-01-01T16:00:00Z",
            net_liquidation=100_000,
            cash=10_000,
            buying_power=50_000,
            margin_requirement=0,
            daily_pnl=0,
            daily_pnl_percent=0,
            positions=[],
        ),
        PortfolioPnLSnapshot(
            date="2026-01-15",
            timestamp="2026-01-15T16:00:00Z",
            net_liquidation=105_000,
            cash=10_000,
            buying_power=50_000,
            margin_requirement=0,
            daily_pnl=5000,
            daily_pnl_percent=5,
            positions=[],
        ),
    ]


def test_modified_dietz_weights_mid_period_deposit():
    transactions = [
        Transaction(
            account_id="TEST-001",
            symbol="CASH",
            trade_date=date(2026, 1, 8),
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
        105_000,
        transactions,
        date(2026, 1, 1),
        date(2026, 1, 15),
        "USD",
        lambda _a, _b: 1.0,
    )
    assert interval_return is not None
    assert interval_return == pytest.approx(0.0, abs=1e-4)


def test_calculation_run_persists_to_state_store(tmp_path, monkeypatch):
    monkeypatch.setenv("PERSISTENCE_BACKEND", "json")
    monkeypatch.setattr("app.db.state_store._data_dir", lambda: str(tmp_path))
    run = create_calculation_run(
        run_type="unit_test",
        account_id="TEST-001",
        input_snapshot_ids=["2026-01-01:open"],
        coverage={"status": "test"},
    )
    loaded = load_calculation_run("TEST-001", run.calculation_run_id)
    assert loaded is not None
    assert loaded.run_type == "unit_test"


def test_score_stock_default_does_not_record_observations(monkeypatch):
    calls: list[tuple] = []

    def _fake_record(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(
        "app.services.scoring.calibration_ingestion.record_score_observation",
        _fake_record,
    )
    score_stock(_position(), allow_mock=True, record_observations=False)
    assert calls == []


def test_score_stock_records_observations_when_enabled(monkeypatch):
    calls: list[tuple] = []

    def _fake_record(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(
        "app.services.scoring.calibration_ingestion.record_score_observation",
        _fake_record,
    )
    monkeypatch.setattr(
        "app.services.scoring.calibration_ingestion.materialize_calibration_observations",
        lambda *args, **kwargs: 0,
    )
    score_stock(_position(), allow_mock=True, record_observations=True)
    assert len(calls) == 1


def test_pnl_decomposition_reports_known_cash_flows(monkeypatch, tmp_path):
    monkeypatch.setenv("PERSISTENCE_BACKEND", "json")
    monkeypatch.setattr("app.services.portfolio.ledger_coverage.DATA_DIR", str(tmp_path))
    monkeypatch.setattr("app.services.portfolio.transaction_store.DATA_DIR", str(tmp_path))
    monkeypatch.setattr("app.db.state_store._data_dir", lambda: str(tmp_path / "state"))
    account_id = "TEST-PNL-DECOMP"
    save_ledger_coverage(
        TransactionLedgerCoverage(
            account_id=account_id,
            source="mock_flex_cash_ledger",
            coverage_start=date(2026, 1, 1),
            coverage_end=date(2026, 1, 15),
            imported_sections=["mock_flex_cash_ledger"],
            status="completed",
        )
    )
    save_transactions(
        account_id,
        [
            Transaction(
                account_id=account_id,
                symbol="AAPL",
                trade_date=date(2026, 1, 10),
                action="dividend",
                quantity=1,
                price=25,
                commission=0,
                currency="USD",
                amount=25,
            )
        ],
    )
    result = calculate_pnl_decomposition(
        account_id,
        _history(),
        [_position()],
        "USD",
        lambda _a, _b: 1.0,
    )
    assert result.dividend_income_total == 25.0
    assert result.price_effect_total is None
    assert result.reconciliation_status == "provisional_cash_flow_inventory"
    assert result.calculation_run["calculation_run_id"]


def test_factor_regression_returns_diagnostics():
    y = [0.01, -0.005, 0.02, 0.003, -0.01] * 26
    factors = [[0.008, -0.004, 0.015, 0.001, -0.008] * 26]
    _, r_squared, _, diagnostics = _matrix_ols(y, factors)
    assert r_squared is not None
    assert diagnostics.get("model_label") == "ETF-proxy exposure model"
    assert diagnostics.get("observation_count") == len(y)


def test_time_weighted_return_still_compounds_intervals():
    twr = calculate_time_weighted_return([0.01, 0.02, -0.005])
    assert twr == pytest.approx((1.01 * 1.02 * 0.995) - 1.0, abs=1e-6)
