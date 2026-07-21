"""Valuation run persistence for Decision Center status lookups."""

from __future__ import annotations

from datetime import date

from app.schemas.domain import FundamentalSnapshot
from app.services.valuation.scenario_valuation import persist_valuation_run, run_scenario_valuation
from app.services.valuation.scenario_valuation import ScenarioValuationResult


def test_persist_valuation_run_writes_state(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PORTFOLIO_DATA_DIR", str(tmp_path))
    from app.core.config import settings

    monkeypatch.setattr(settings, "persistence_backend", "json")
    result = ScenarioValuationResult(
        symbol="AAPL",
        company_type="general_operating",
        valuation_status="available",
        fair_value_mid=100.0,
        methodology="test",
    )
    persist_valuation_run(result)
    from app.db.state_store import get_state_store

    row = get_state_store().read_json("valuation_runs", "latest:AAPL")
    assert row["status"] == "approved_for_personal_use"
    assert row["methodology_status"] == "approved_for_personal_use"


def test_run_scenario_valuation_persists_withheld_without_price(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PORTFOLIO_DATA_DIR", str(tmp_path))
    from app.core.config import settings

    monkeypatch.setattr(settings, "persistence_backend", "json")
    snapshot = FundamentalSnapshot(
        symbol="MSFT",
        period="TTM",
        report_date=date(2024, 1, 1),
        source="test",
        currency="USD",
    )
    result = run_scenario_valuation(snapshot, market_price=None)
    assert result.valuation_status == "unavailable"
    from app.db.state_store import get_state_store

    row = get_state_store().read_json("valuation_runs", "latest:MSFT")
    assert row["status"] == "withheld"
