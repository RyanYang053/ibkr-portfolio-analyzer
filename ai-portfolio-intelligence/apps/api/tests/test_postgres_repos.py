import os
from datetime import date, datetime, timezone

import pytest

from app.schemas.domain import FundamentalSnapshot, Transaction
from app.services.fundamentals.providers.yahoo_enrichment import enrich_sector_fields
from app.services.portfolio.ledger_coverage import TransactionLedgerCoverage


def test_financials_yahoo_enrichment_does_not_fabricate_sector_metrics():
    snapshot = FundamentalSnapshot(
        symbol="JPM",
        period="TTM",
        report_date=date(2025, 12, 31),
        revenue_growth_yoy=0.05,
        gross_margin=0.4,
        operating_margin=0.3,
        free_cash_flow=1_000_000.0,
        cash=10_000_000.0,
        total_debt=5_000_000.0,
        pe_forward=12.0,
        ev_sales=3.0,
        fcf_yield=0.04,
    )
    enriched = enrich_sector_fields(
        snapshot,
        "Financials",
        stats={"priceToBook": {"raw": 1.2}, "returnOnEquity": {"raw": 0.15}},
        financial_data={"operatingMargins": {"raw": 0.035}},
    )
    assert enriched.price_to_tangible_book is None
    assert enriched.return_on_equity is None
    assert enriched.net_interest_margin is None


def test_reit_yahoo_enrichment_does_not_fabricate_sector_metrics():
    snapshot = FundamentalSnapshot(
        symbol="O",
        period="TTM",
        report_date=date(2025, 12, 31),
        revenue_growth_yoy=0.03,
        gross_margin=0.5,
        operating_margin=0.35,
        free_cash_flow=1_000_000.0,
        cash=1_000_000.0,
        total_debt=2_000_000.0,
        pe_forward=15.0,
        ev_sales=8.0,
        fcf_yield=0.05,
    )
    enriched = enrich_sector_fields(
        snapshot,
        "Real Estate",
        stats={"trailingEps": {"raw": 2.5}},
        financial_data={"operatingMargins": {"raw": 0.4}},
    )
    assert enriched.ffo_per_share is None
    assert enriched.occupancy_rate is None


def test_mock_financials_include_sector_fields_for_financials():
    from app.services.fundamentals.providers import get_fundamental_provider

    snapshot = get_fundamental_provider(allow_mock=True).get_fundamentals("SOFI")
    assert snapshot.price_to_tangible_book is not None
    assert snapshot.return_on_equity is not None
    assert snapshot.net_interest_margin is not None


@pytest.fixture
def postgres_backend(monkeypatch):
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not configured")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("PERSISTENCE_BACKEND", "postgres")
    monkeypatch.setattr("app.core.config.settings.database_url", database_url)
    monkeypatch.setattr("app.core.config.settings.persistence_backend", "postgres")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    test_engine = create_engine(database_url, pool_pre_ping=True)
    session_factory = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)
    monkeypatch.setattr("app.db.session.engine", test_engine)
    monkeypatch.setattr("app.db.session.SessionLocal", session_factory)
    monkeypatch.setattr("app.db.ledger_transaction_repo.SessionLocal", session_factory)
    monkeypatch.setattr("app.db.ledger_coverage_repo.SessionLocal", session_factory)
    monkeypatch.setattr("app.db.pnl_snapshot_repo.SessionLocal", session_factory)
    monkeypatch.setattr("app.db.fundamental_snapshot_repo.SessionLocal", session_factory)
    monkeypatch.setattr("app.db.fx_rate_repo.SessionLocal", session_factory)
    monkeypatch.setattr("app.db.user_repo.SessionLocal", session_factory)
    monkeypatch.setattr("app.db.account_access_repo.SessionLocal", session_factory)
    yield


def test_ledger_transaction_repo_roundtrip(postgres_backend):
    from app.db.ledger_transaction_repo import read_transactions, replace_transactions

    account_id = "PG-TEST-LEDGER"
    txn = Transaction(
        account_id=account_id,
        transaction_id="txn-1",
        symbol="MSFT",
        con_id=272093,
        trade_date=date(2026, 1, 5),
        action="buy",
        quantity=10.0,
        price=400.0,
        commission=1.0,
        currency="USD",
        source="test",
    )
    replace_transactions(account_id, [txn])
    rows = read_transactions(account_id)
    assert rows is not None
    assert len(rows) == 1
    assert rows[0]["symbol"] == "MSFT"
    assert rows[0]["con_id"] == 272093


def test_ledger_coverage_repo_roundtrip(postgres_backend):
    from app.db.ledger_coverage_repo import read_coverage, upsert_coverage

    account_id = "PG-TEST-COVERAGE"
    coverage = TransactionLedgerCoverage(
        account_id=account_id,
        source="ibkr_flex",
        coverage_start=date(2025, 1, 1),
        coverage_end=date(2026, 1, 1),
        status="completed",
    )
    upsert_coverage(coverage)
    payload = read_coverage(account_id)
    assert payload is not None
    assert payload["status"] == "completed"


def test_pnl_snapshot_repo_roundtrip(postgres_backend):
    from app.db.pnl_snapshot_repo import read_pnl_snapshots, upsert_pnl_snapshot

    account_id = "PG-TEST-PNL"
    snapshot = {
        "date": "2026-01-05",
        "net_liquidation": 100000.0,
        "cash": 10000.0,
        "source": "test",
    }
    upsert_pnl_snapshot(account_id, date(2026, 1, 5), snapshot)
    history = read_pnl_snapshots(account_id)
    assert history is not None
    assert history[0]["net_liquidation"] == 100000.0


def test_fundamental_snapshot_repo_roundtrip(postgres_backend):
    from app.db.fundamental_snapshot_repo import list_snapshot_records, upsert_snapshot_record
    from app.schemas.domain import FundamentalSnapshot, FundamentalSnapshotRecord

    record = FundamentalSnapshotRecord(
        symbol="MSFT",
        as_of_date=date(2026, 1, 5),
        snapshot=FundamentalSnapshot(
            symbol="MSFT",
            period="TTM",
            report_date=date(2026, 1, 5),
            revenue_growth_yoy=0.1,
            gross_margin=0.6,
            operating_margin=0.3,
            free_cash_flow=1_000_000.0,
            cash=10_000_000.0,
            total_debt=2_000_000.0,
            pe_forward=25.0,
            ev_sales=8.0,
            fcf_yield=0.03,
            source="test",
        ),
        point_in_time=True,
        source="test",
        ingested_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
    )
    upsert_snapshot_record(record)
    rows = list_snapshot_records("MSFT")
    assert rows is not None
    assert len(rows) == 1
    assert rows[0].snapshot.symbol == "MSFT"


def test_fx_rate_repo_roundtrip(postgres_backend):
    from app.db.fx_rate_repo import load_rate_series, lookup_rate, upsert_rate_series

    upsert_rate_series("USD", "CAD", {"2026-01-05": 1.35, "2026-01-06": 1.36})
    series = load_rate_series("USD", "CAD")
    assert series is not None
    assert series["2026-01-05"] == 1.35
    assert lookup_rate("USD", "CAD", date(2026, 1, 5)) == 1.35
