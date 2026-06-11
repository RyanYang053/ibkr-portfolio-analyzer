"""Unit tests for the PnL tracker service."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from app.services.portfolio.pnl_tracker import (
    HISTORY_FILE,
    PortfolioPnLSnapshot,
    PositionPnL,
    get_pnl_history,
    record_pnl_snapshot,
)
from app.schemas.domain import AccountSummary, Position, utc_now


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_history(tmp_path):
    """Redirect the PnL history file to a temp directory so tests are isolated."""
    tmp_file = str(tmp_path / "pnl_history.json")
    with patch("app.services.portfolio.pnl_tracker.HISTORY_FILE", tmp_file), \
         patch("app.services.portfolio.pnl_tracker.DATA_DIR", str(tmp_path)):
        yield tmp_file


def _make_summary(
    net_liq: float = 156000.0,
    cash: float = 32500.0,
    buying_power: float = 125000.0,
    margin_req: float = 18500.0,
) -> AccountSummary:
    return AccountSummary(
        account_id="TEST",
        net_liquidation=net_liq,
        cash=cash,
        buying_power=buying_power,
        margin_requirement=margin_req,
        excess_liquidity=net_liq - margin_req,
        total_unrealized_pnl=4200.0,
        total_realized_pnl=1200.0,
        base_currency="USD",
        data_timestamp=utc_now(),
    )


def _make_position(symbol: str = "AAPL", qty: float = 50, price: float = 190.0) -> Position:
    return Position(
        account_id="TEST",
        symbol=symbol,
        company_name=f"{symbol} Inc.",
        asset_class="STK",
        quantity=qty,
        avg_cost=180.0,
        market_price=price,
        market_value=qty * price,
        unrealized_pnl=(price - 180.0) * qty,
        realized_pnl=0.0,
        currency="USD",
        exchange="SMART",
        sector="Technology",
        industry="Hardware",
        portfolio_weight=10.0,
        stock_type="core",
        is_etf=False,
        is_speculative=False,
        updated_at=utc_now(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGetPnlHistory:
    """Tests for reading / initializing PnL history."""

    def test_empty_file_triggers_mock_history(self, _isolate_history):
        """When no history file exists, mock history is seeded automatically."""
        history = get_pnl_history()
        assert len(history) > 0, "Mock history should be pre-populated"
        for entry in history:
            assert isinstance(entry, PortfolioPnLSnapshot)

    def test_mock_history_has_business_days_only(self, _isolate_history):
        """Generated mock data should skip weekends."""
        history = get_pnl_history()
        for entry in history:
            d = date.fromisoformat(entry.date)
            assert d.weekday() < 5, f"Date {entry.date} is a weekend day"

    def test_mock_history_has_positions(self, _isolate_history):
        """Each mock entry should contain position-level detail."""
        history = get_pnl_history()
        for entry in history:
            assert isinstance(entry.positions, list)
            assert len(entry.positions) > 0, f"Entry {entry.date} has no positions"

    def test_history_persists_to_json(self, _isolate_history):
        """After initialization, the JSON file should exist and be valid."""
        get_pnl_history()
        assert os.path.exists(_isolate_history)
        with open(_isolate_history, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_reload_returns_same_data(self, _isolate_history):
        """Calling get_pnl_history twice returns the same persisted data."""
        first = get_pnl_history()
        second = get_pnl_history()
        assert len(first) == len(second)
        assert first[0].date == second[0].date


class TestRecordSnapshot:
    """Tests for recording a new PnL snapshot."""

    def test_record_appends_entry(self, _isolate_history):
        """A new snapshot should be appended and persisted."""
        summary = _make_summary()
        positions = [_make_position()]
        snapshot = record_pnl_snapshot(summary, positions)

        assert isinstance(snapshot, PortfolioPnLSnapshot)
        assert snapshot.date == date.today().isoformat()
        assert snapshot.net_liquidation == 156000.0
        assert snapshot.cash == 32500.0

        # Verify it's in the full history
        history = get_pnl_history()
        today_entries = [h for h in history if h.date == date.today().isoformat()]
        assert len(today_entries) == 1

    def test_daily_pnl_calculation(self, _isolate_history):
        """Daily PnL should reflect the change from the previous entry."""
        # First, seed the history
        get_pnl_history()
        history = get_pnl_history()
        # Filter out today to get the true "previous day" entry for comparison
        today_str = date.today().isoformat()
        previous_entries = [h for h in history if h.date != today_str]
        last_entry = previous_entries[-1] if previous_entries else history[-1]
        last_net_liq = last_entry.net_liquidation

        # Record a new snapshot with a known net_liq
        delta = 500.0
        new_net_liq = last_net_liq + delta
        summary = _make_summary(net_liq=new_net_liq)
        snapshot = record_pnl_snapshot(summary, [])

        expected_pnl = new_net_liq - last_net_liq
        assert abs(snapshot.daily_pnl - expected_pnl) < 0.01
        expected_pct = (expected_pnl / last_net_liq) * 100
        assert abs(snapshot.daily_pnl_percent - expected_pct) < 0.01

    def test_dedup_same_day(self, _isolate_history):
        """Recording twice on the same day should replace, not double-add."""
        summary1 = _make_summary(net_liq=150000.0)
        summary2 = _make_summary(net_liq=160000.0)

        record_pnl_snapshot(summary1, [])
        record_pnl_snapshot(summary2, [])

        history = get_pnl_history()
        today_entries = [h for h in history if h.date == date.today().isoformat()]
        assert len(today_entries) == 1
        assert today_entries[0].net_liquidation == 160000.0

    def test_position_level_pnl(self, _isolate_history):
        """Position-level daily PnL should be calculated when previous entry exists."""
        # Seed history first
        get_pnl_history()

        positions = [_make_position("MSFT", qty=100, price=425.0)]
        summary = _make_summary(net_liq=170000.0)
        snapshot = record_pnl_snapshot(summary, positions)

        assert len(snapshot.positions) == 1
        assert snapshot.positions[0].symbol == "MSFT"
        assert snapshot.positions[0].market_price == 425.0

    def test_zero_quantity_positions_excluded(self, _isolate_history):
        """Positions with qty <= 0 should be filtered out."""
        pos = _make_position("SOLD", qty=0, price=100.0)
        summary = _make_summary()
        snapshot = record_pnl_snapshot(summary, [pos])
        assert len(snapshot.positions) == 0


class TestSnapshotModel:
    """Tests for the Pydantic model serialization."""

    def test_snapshot_roundtrip(self):
        """A snapshot should serialize and deserialize identically."""
        snapshot = PortfolioPnLSnapshot(
            date="2026-06-10",
            timestamp="2026-06-10T20:00:00+00:00",
            net_liquidation=156000.0,
            cash=32500.0,
            buying_power=125000.0,
            margin_requirement=18500.0,
            daily_pnl=920.0,
            daily_pnl_percent=0.59,
            positions=[
                PositionPnL(
                    symbol="AAPL",
                    quantity=50,
                    market_price=190.0,
                    market_value=9500.0,
                    unrealized_pnl=500.0,
                    daily_pnl=120.0,
                    daily_pnl_percent=0.63,
                )
            ],
        )
        data = snapshot.model_dump()
        restored = PortfolioPnLSnapshot(**data)
        assert restored.net_liquidation == snapshot.net_liquidation
        assert restored.positions[0].symbol == "AAPL"
        assert restored.daily_pnl == 920.0
