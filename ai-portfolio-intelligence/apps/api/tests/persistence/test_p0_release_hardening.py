"""Release A (plan §25) P0 hardening regression tests.

Covers:
- P0.1 fail-closed SQLite schema initialization
- P0.2 core financial state persists canonically to SQLite (not raw JSON files)
- P0.3 tax reconciliation payloads are serialized before binding to raw SQL
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def sqlite_backend(tmp_path, monkeypatch):
    """Bind the app to a real temp SQLite database with Decision OS tables created."""
    db_path = Path(tmp_path) / "portfolio.db"
    monkeypatch.setenv("PORTFOLIO_DATA_DIR", str(tmp_path))
    from app.core.config import settings

    monkeypatch.setattr(settings, "persistence_backend", "sqlite")
    monkeypatch.setattr(settings, "database_url", f"sqlite+pysqlite:///{db_path}")

    import app.db.session as session_mod

    session_mod.engine = session_mod._build_engine()
    session_mod.SessionLocal = sessionmaker(bind=session_mod.engine, autocommit=False, autoflush=False)

    from app.db import state_store as state_store_mod

    state_store_mod._SQLITE_TABLE_READY = False

    from app.db.sqlite_desktop_schema import ensure_decision_os_sqlite_tables

    result = ensure_decision_os_sqlite_tables()
    assert result["ok"] is True
    return db_path


# --------------------------------------------------------------------------- P0.1


def test_schema_init_reports_ok_and_creates_required_tables(sqlite_backend):
    from sqlalchemy import inspect

    import app.db.session as session_mod

    tables = set(inspect(session_mod.engine).get_table_names())
    for required in ("decision_packets", "evidence_records", "financial_plans", "monitoring_events"):
        assert required in tables


def test_bootstrap_fails_closed_when_schema_init_fails(tmp_path, monkeypatch):
    """A schema-init failure must abort startup, never boot on a broken schema."""
    monkeypatch.setenv("PORTFOLIO_DATA_DIR", str(tmp_path))
    from app.core.config import DeploymentMode, settings

    monkeypatch.setattr(settings, "persistence_backend", "sqlite")
    monkeypatch.setattr(settings, "deployment_mode", DeploymentMode.DESKTOP_LOCAL)
    monkeypatch.setattr(settings, "database_url", f"sqlite+pysqlite:///{tmp_path}/portfolio.db")

    import app.db.sqlite_desktop_schema as schema_mod

    monkeypatch.setattr(
        schema_mod, "ensure_decision_os_sqlite_tables", lambda: {"ok": False, "error": "simulated failure"}
    )

    from app.core.desktop_bootstrap import bootstrap_desktop_persistence

    with pytest.raises(RuntimeError, match="schema initialization failed"):
        bootstrap_desktop_persistence()


# --------------------------------------------------------------------------- P0.2


def _txn(account_id: str, symbol: str = "AAPL") -> "object":
    from app.schemas.domain import Transaction

    return Transaction(
        account_id=account_id,
        symbol=symbol,
        trade_date=date(2024, 3, 1),
        action="buy",
        quantity=10,
        price=100.0,
        amount=-1000.0,
        currency="USD",
        source="test",
    )


def test_transactions_persist_to_sqlite_not_json_files(sqlite_backend, monkeypatch):
    """Under sqlite, the transaction ledger must live in SQLite, not a raw JSON file."""
    from app.services.portfolio import transaction_store

    # Point the legacy JSON path at an isolated dir and prove it stays empty.
    json_dir = sqlite_backend.parent / "legacy_json"
    monkeypatch.setattr(transaction_store, "DATA_DIR", str(json_dir))

    account = "U-TEST-1"
    transaction_store.save_transactions(account, [_txn(account)])

    loaded = transaction_store.load_transactions(account)
    assert len(loaded) == 1
    assert loaded[0].symbol == "AAPL"

    # No raw JSON ledger file was written.
    assert not json_dir.exists() or not list(json_dir.glob("transactions_*.json"))

    # The data is in the SQLite state store.
    from app.db.state_store import get_state_store

    stored = get_state_store().read_json("transaction_ledger", account, default=None)
    assert stored is not None and len(stored) == 1


def test_fundamentals_persist_to_sqlite(sqlite_backend, monkeypatch):
    """P0.2 follow-up: fundamental snapshots persist to SQLite, not raw JSON files."""
    from datetime import date

    from app.schemas.domain import FundamentalSnapshot, FundamentalSnapshotRecord
    from app.services.fundamentals import snapshot_store

    json_dir = sqlite_backend.parent / "fund_json"
    monkeypatch.setattr(snapshot_store, "DATA_DIR", str(json_dir))

    record = FundamentalSnapshotRecord(
        symbol="MSFT",
        as_of_date=date(2024, 3, 31),
        snapshot=FundamentalSnapshot(symbol="MSFT", period="Q1", report_date=date(2024, 3, 31)),
        point_in_time=True,
        source="test",
    )
    snapshot_store.save_snapshot_record(record)

    loaded = snapshot_store.list_snapshot_records("MSFT")
    assert any(r.symbol == "MSFT" for r in loaded)
    assert not json_dir.exists() or not list(json_dir.glob("fundamentals_*.json"))

    from app.db.state_store import get_state_store

    assert get_state_store().read_json("fundamental_snapshots", "MSFT", default=None) is not None


def test_fx_history_persists_to_sqlite(sqlite_backend):
    from app.services.market_data import fx_store

    fx_store._save_store({"USD_CAD": {"2024-03-01": 1.35}})
    assert fx_store._load_store()["USD_CAD"]["2024-03-01"] == 1.35

    from app.db.state_store import get_state_store

    assert get_state_store().read_json("fx_rate_history", "store", default=None) is not None


# --------------------------------------------------------------------------- P0.3


def test_tax_reconciliation_run_persists_with_serialized_payload(sqlite_backend):
    """The reconciliation payload (a dict) must be json-serialized before binding to SQL."""
    from app.db.tax_reconciliation_repo import (
        get_tax_reconciliation_run,
        save_tax_reconciliation_run,
    )

    payload = {"lot_count": 3, "unresolved_items": ["missing_basis"], "order_generated": False}
    row = save_tax_reconciliation_run(
        account_id="U-TEST-1", tax_year=2024, status="reconciled", payload=payload
    )
    rid = row["run_id"]

    # Row is present in the SQLite table with a JSON payload (no dict-binding error).
    from sqlalchemy import text

    import app.db.session as session_mod

    with session_mod.SessionLocal() as session:
        db_row = session.execute(
            text("SELECT status, payload_json FROM tax_reconciliation_runs WHERE run_id = :rid"),
            {"rid": rid},
        ).fetchone()
    assert db_row is not None
    assert db_row[0] == "reconciled"

    fetched = get_tax_reconciliation_run(rid)
    assert fetched is not None
    assert fetched["status"] == "reconciled"


def test_export_includes_portfolio_db_under_sqlite(sqlite_backend):
    """P0.5: the user-facing export must include the canonical SQLite database."""
    import json
    import zipfile

    from app.core.desktop_bootstrap import export_desktop_archive

    export_path = export_desktop_archive()
    with zipfile.ZipFile(export_path, "r") as archive:
        names = archive.namelist()
        manifest = json.loads(archive.read("export-manifest.json").decode("utf-8"))
    assert "portfolio.db" in names
    assert any(entry["path"] == "portfolio.db" for entry in manifest["files"])


def test_now_is_timezone_aware():
    """Guard: timestamps used in persistence are tz-aware UTC."""
    from app.db.tax_reconciliation_repo import _now

    assert _now().tzinfo is not None
    assert _now().utcoffset() == datetime.now(timezone.utc).utcoffset()
