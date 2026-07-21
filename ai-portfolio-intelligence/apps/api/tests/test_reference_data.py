"""Reference-data ingestion into §17 tables (price_bars/quotes/catalysts/corp actions)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.main import app


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


def test_price_bars_persist_and_read_back(sqlite_backend):
    from app.db.reference_data_repo import list_price_bars, save_price_bars

    bars = [
        {"date": "2024-03-01", "open": 400, "high": 410, "low": 395, "close": 405},
        {"date": "2024-03-02", "open": 405, "high": 415, "low": 402, "close": 412},
    ]
    assert save_price_bars("MSFT:272093", "1d", bars) == 2
    read = list_price_bars("MSFT:272093", "1d")
    assert len(read) == 2
    assert any(b["close"] == 412 for b in read)


def test_quote_catalyst_corporate_action_persist(sqlite_backend):
    from app.db.reference_data_repo import save_catalyst, save_corporate_action, save_quote

    assert save_quote("MSFT:1", {"price": 405.0, "currency": "USD"}) is True
    assert save_catalyst("cat_x", "MSFT:1", "earnings", {"event_date": "2024-04-25"}) is True
    assert save_corporate_action("ca_x", "AAPL:1", "corporate_action", {"kind": "split"}) is True

    from sqlalchemy import text

    with sqlite_backend.SessionLocal() as s:
        assert s.execute(text("SELECT COUNT(*) FROM quotes")).scalar() == 1
        assert s.execute(text("SELECT COUNT(*) FROM catalysts")).scalar() == 1
        assert s.execute(text("SELECT COUNT(*) FROM corporate_actions")).scalar() == 1


def test_corporate_action_parsing_from_transaction(sqlite_backend):
    from app.schemas.domain import Transaction
    from app.services.portfolio.corporate_actions import parse_corporate_action

    txn = Transaction(
        account_id="A1", symbol="AAPL", trade_date=date(2024, 6, 1),
        event_timestamp=datetime(2024, 6, 1, tzinfo=timezone.utc),
        action="corporate_action", quantity=0, price=0, amount=0, currency="USD", source="flex",
    )
    # parse returns a CorporateAction or None; either way it must not raise.
    parse_corporate_action(txn)


def test_chart_endpoint_still_works_with_persistence():
    # In json mode persistence no-ops; the endpoint must remain functional.
    orig = settings.broker_mode
    settings.broker_mode = "mock_ibkr_readonly"
    try:
        client = TestClient(app)
        res = client.get("/research/catalysts?account_id=MOCK-001")
        assert res.status_code == 200
    finally:
        settings.broker_mode = orig
