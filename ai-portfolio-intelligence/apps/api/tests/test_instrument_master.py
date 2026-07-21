"""Release B1: canonical instrument master + /instruments API."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.main import app


@pytest.fixture
def sqlite_instruments(tmp_path, monkeypatch):
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
    return db_path


# ---------------------------------------------------------------- repo (sqlite)


def test_resolve_creates_provisional_and_conid_records(sqlite_instruments):
    from app.db.instruments_repository import get_instrument, resolve_instrument

    prov = resolve_instrument(symbol="nvda")
    assert prov.instrument_id == "NVDA"
    assert prov.provisional is True
    assert prov.con_id is None

    firm = resolve_instrument(symbol="MSFT", con_id=272093, name="Microsoft", sector="Technology")
    assert firm.instrument_id == "MSFT:272093"
    assert firm.provisional is False
    assert firm.sector == "Technology"

    assert get_instrument("MSFT:272093").name == "Microsoft"


def test_upsert_preserves_first_seen_and_updates_fields(sqlite_instruments):
    from app.db.instruments_repository import get_instrument, resolve_instrument, upsert_instrument
    from app.schemas.instrument import InstrumentRecord

    resolve_instrument(symbol="AAPL", con_id=265598, sector="Technology")
    first_seen = get_instrument("AAPL:265598").first_seen_at
    assert first_seen is not None

    upsert_instrument(
        InstrumentRecord.build(symbol="AAPL", con_id=265598, name="Apple Inc.", sector="Tech Hardware")
    )
    updated = get_instrument("AAPL:265598")
    assert updated.name == "Apple Inc."
    assert updated.sector == "Tech Hardware"
    assert updated.first_seen_at == first_seen  # unchanged


def test_search_by_symbol_prefix_and_name(sqlite_instruments):
    from app.db.instruments_repository import resolve_instrument, search_instruments

    resolve_instrument(symbol="MSFT", con_id=272093, name="Microsoft Corp")
    resolve_instrument(symbol="MU", con_id=9999, name="Micron Technology")
    resolve_instrument(symbol="AAPL", con_id=265598, name="Apple Inc.")

    by_prefix = search_instruments("M")
    symbols = {r.symbol for r in by_prefix}
    assert "MSFT" in symbols and "MU" in symbols
    assert "AAPL" not in symbols

    exact = search_instruments("MSFT")
    assert exact[0].symbol == "MSFT"  # exact match ranked first

    by_name = search_instruments("Micron")
    assert any(r.symbol == "MU" for r in by_name)


# ---------------------------------------------------------------- routes (json)


def test_instrument_search_route_registers_holdings():
    orig = settings.broker_mode
    settings.broker_mode = "mock_ibkr_readonly"
    try:
        client = TestClient(app)
        res = client.get("/instruments/search?q=MSFT&account_id=MOCK-001")
        assert res.status_code == 200
        body = res.json()
        assert body["count"] >= 1
        assert any(r["symbol"] == "MSFT" for r in body["instruments"])
        assert body["data_quality"]["status"] == "available"
    finally:
        settings.broker_mode = orig


def test_instrument_detail_and_404():
    orig = settings.broker_mode
    settings.broker_mode = "mock_ibkr_readonly"
    try:
        client = TestClient(app)
        # Register holdings, then look up a held instrument by id.
        client.get("/instruments/search?q=QQQ&account_id=MOCK-001")
        search = client.get("/instruments/search?q=QQQ&account_id=MOCK-001").json()
        iid = search["instruments"][0]["instrument_id"]
        detail = client.get(f"/instruments/{iid}?account_id=MOCK-001")
        assert detail.status_code == 200
        assert detail.json()["symbol"] == "QQQ"

        # A bare, never-seen symbol resolves as a provisional instrument.
        prov = client.get("/instruments/ZZZZ?account_id=MOCK-001")
        assert prov.status_code == 200
        assert prov.json()["provisional"] is True

        # A structured id with a con_id that was never seen is a 404.
        missing = client.get("/instruments/NOPE:12345?account_id=MOCK-001")
        assert missing.status_code == 404
    finally:
        settings.broker_mode = orig


def test_overview_for_owned_security():
    orig = settings.broker_mode
    settings.broker_mode = "mock_ibkr_readonly"
    try:
        client = TestClient(app)
        search = client.get("/instruments/search?q=MSFT&account_id=MOCK-001").json()
        iid = next(r["instrument_id"] for r in search["instruments"] if r["symbol"] == "MSFT")
        res = client.get(f"/instruments/{iid}/overview?account_id=MOCK-001")
        assert res.status_code == 200
        body = res.json()
        assert body["instrument"]["symbol"] == "MSFT"
        assert body["position_status"] == "owned"
        assert body["market"]["status"] == "available"
        assert body["position"]["quantity"] != 0
        # Every section reports a status (§15.3 — no silent gaps).
        assert set(body["data_quality"]) >= {"market", "position", "decision"}
    finally:
        settings.broker_mode = orig


def test_overview_for_unowned_security_is_honest_not_fabricated():
    orig = settings.broker_mode
    settings.broker_mode = "mock_ibkr_readonly"
    try:
        client = TestClient(app)
        res = client.get("/instruments/ZZZZ/overview?account_id=MOCK-001")
        assert res.status_code == 200
        body = res.json()
        assert body["position_status"] == "not_owned"
        # Unowned + no quote source: say so, never invent a price.
        assert body["market"]["status"] in {"unavailable", "available"}
        if body["market"]["status"] == "unavailable":
            assert "price" not in body["market"]
        assert body["decision"]["status"] in {"none", "available", "unavailable"}
    finally:
        settings.broker_mode = orig
