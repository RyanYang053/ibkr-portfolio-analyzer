"""Remaining §17 tables: existence + real usage (risk snapshots, app settings)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

_SECTION17_TABLES = {
    "risk_snapshots",
    "stress_test_runs",
    "catalysts",
    "catalyst_outcomes",
    "performance_periods",
    "construction_scenarios",
    "price_bars",
    "quotes",
    "corporate_actions",
    "estimate_points",
    "application_settings",
    "option_positions",
    "option_strategy_groups",
    "option_risk_snapshots",
    "option_scenario_runs",
}


@pytest.fixture
def sqlite_backend(tmp_path, monkeypatch):
    db_path = Path(tmp_path) / "portfolio.db"
    monkeypatch.setenv("PORTFOLIO_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "persistence_backend", "sqlite")
    monkeypatch.setattr(settings, "database_url", f"sqlite+pysqlite:///{db_path}")
    import app.db.session as session_mod

    session_mod.engine = session_mod._build_engine()
    session_mod.SessionLocal = sessionmaker(bind=session_mod.engine, autocommit=False, autoflush=False)
    from app.db import state_store as state_store_mod

    state_store_mod._SQLITE_TABLE_READY = False
    from app.db.sqlite_desktop_schema import ensure_decision_os_sqlite_tables

    assert ensure_decision_os_sqlite_tables()["ok"] is True
    return session_mod


def test_all_section17_tables_created(sqlite_backend):
    present = set(inspect(sqlite_backend.engine).get_table_names())
    missing = _SECTION17_TABLES - present
    assert not missing, f"missing §17 tables: {missing}"


def test_domain_repos_roundtrip_payload_under_sqlite(sqlite_backend):
    """Guard against the json_cast regression: payloads must read back intact under
    the shipped sqlite backend (not stored as 0)."""
    from app.db.journal_repo import get_journal_entry, save_journal_entry
    from app.db.market_repo import latest_market_regime, save_market_regime
    from app.db.trade_plan_repo import get_trade_plan, save_trade_plan
    from app.schemas.journal import JournalEntry
    from app.schemas.market import MarketRegime, RegimeInputs, RegimeState
    from app.schemas.trade_plan import TradeDirection, TradePlan

    plan = TradePlan(trade_plan_id="tp_rt", account_id="A1", instrument_id="MSFT:1", symbol="MSFT",
                     direction=TradeDirection.BUY, proposed_quantity=42.0)
    save_trade_plan(plan)
    assert get_trade_plan("tp_rt").proposed_quantity == 42.0  # not 0/None

    entry = JournalEntry(entry_id="je_rt", account_id="A1", instrument_id="MSFT:1", symbol="MSFT", entry_thesis="x")
    save_journal_entry(entry)
    assert get_journal_entry("je_rt").entry_thesis == "x"

    regime = MarketRegime(label=RegimeState.RANGE_BOUND, confidence=0.5, dimensions=RegimeInputs(trend="flat"))
    save_market_regime(regime)
    assert latest_market_regime().label == RegimeState.RANGE_BOUND


def test_risk_snapshot_and_settings_persist(sqlite_backend):
    from app.db.analytics_snapshot_repo import save_risk_snapshot
    from app.db.app_settings_repo import all_settings, get_setting, set_setting

    sid = save_risk_snapshot("A1", {"risk_score": 42})
    assert sid is not None

    set_setting("local-owner", "theme", {"mode": "light"})
    assert get_setting("local-owner", "theme")["mode"] == "light"
    assert "theme" in all_settings("local-owner")
