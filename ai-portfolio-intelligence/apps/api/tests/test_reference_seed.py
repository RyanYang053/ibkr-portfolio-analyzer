"""Tests for the FinanceDatabase instrument seed mapping + vendored data."""

from __future__ import annotations

import itertools

from app.services import reference_seed as rs

EQUITY_ROW = {
    "symbol": "aapl", "name": "Apple Inc.", "currency": "USD", "sector": "Technology",
    "industry": "Consumer Electronics", "exchange": "NASDAQ", "mic": "XNAS",
    "isin": "US0378331005", "cusip": "037833100", "figi": "BBG000B9XRY4", "composite_figi": "BBG000B9XVV8",
}
ETF_ROW = {
    "symbol": "spy", "name": "SPDR S&P 500 ETF Trust", "currency": "USD",
    "category_group": "Equities", "category": "Large Blend", "exchange": "NYSE Arca",
    "mic": "ARCX", "isin": "US78462F1030",
}


def test_row_to_record_equity():
    rec = rs.row_to_record(EQUITY_ROW, is_etf=False)
    assert rec.symbol == "AAPL"  # normalized upper
    assert rec.instrument_id == "AAPL"
    assert rec.asset_class == "STK"
    assert rec.is_etf is False
    assert rec.sector == "Technology"
    assert rec.industry == "Consumer Electronics"
    assert rec.exchange == "NASDAQ"


def test_row_to_record_etf():
    rec = rs.row_to_record(ETF_ROW, is_etf=True)
    assert rec.symbol == "SPY"
    assert rec.asset_class == "ETF"
    assert rec.is_etf is True
    assert rec.sector == "Equities"  # category_group -> sector
    assert rec.industry == "Large Blend"  # category -> industry


def test_alias_tokens_extracts_cross_ids_and_skips_blanks():
    assert rs.alias_tokens(EQUITY_ROW) == [
        "US0378331005", "037833100", "BBG000B9XRY4", "BBG000B9XVV8",
    ]
    assert rs.alias_tokens(ETF_ROW) == ["US78462F1030"]
    assert rs.alias_tokens({"symbol": "X", "isin": "", "cusip": "  "}) == []
    # a token equal to the symbol is not a useful alias
    assert rs.alias_tokens({"symbol": "AAA", "isin": "aaa"}) == []


def test_vendored_equities_reference_parses_and_maps():
    path = rs.DATA_DIR / "equities_reference.csv"
    assert path.exists(), "vendored equities_reference.csv missing"
    rows = list(itertools.islice(rs._rows(path), 100))
    assert len(rows) == 100
    records = [rs.row_to_record(r, is_etf=False) for r in rows]
    assert all(rec.symbol and rec.asset_class == "STK" for rec in records)
    assert any(rs.alias_tokens(r) for r in rows), "expected ISIN/FIGI aliases in real data"


def test_vendored_etfs_reference_parses_and_maps():
    path = rs.DATA_DIR / "etfs_reference.csv"
    assert path.exists(), "vendored etfs_reference.csv missing"
    rows = list(itertools.islice(rs._rows(path), 50))
    assert len(rows) == 50
    records = [rs.row_to_record(r, is_etf=True) for r in rows]
    assert all(rec.is_etf and rec.asset_class == "ETF" for rec in records)
