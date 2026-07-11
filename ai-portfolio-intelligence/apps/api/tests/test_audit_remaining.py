from __future__ import annotations

from datetime import date

from app.db.broker_sync_batch_repo import create_broker_sync_batch, read_broker_sync_batch
from app.schemas.domain import Position, utc_now
from app.services.attribution.benchmark_weights import benchmark_sector_weights_as_of
from app.services.attribution.engine import calculate_brinson_attribution
from app.services.options.engine import calculate_bs_greeks
from app.services.research.event_taxonomy import classify_news_event


def _position(symbol: str = "MSFT", sector: str = "Technology", market_value: float = 30000) -> Position:
    return Position(
        account_id="TEST-001",
        symbol=symbol,
        company_name=symbol,
        asset_class="STK",
        quantity=100,
        avg_cost=100,
        market_price=market_value / 100,
        market_value=market_value,
        unrealized_pnl=1000,
        currency="USD",
        exchange="NASDAQ",
        sector=sector,
        industry="Software",
        portfolio_weight=10,
        stock_type="mega_cap_quality",
        updated_at=utc_now(),
    )


def test_benchmark_sector_weights_are_date_aware():
    weights = benchmark_sector_weights_as_of(date(2024, 6, 1), allow_mock=True)
    assert weights
    assert abs(sum(weights.values()) - 1.0) < 1e-6


def test_brinson_emits_sector_effects_with_mock_returns():
    positions = [_position("MSFT", "Technology"), _position("JPM", "Financials", 10000)]
    sector_returns = {"Technology": 0.05, "Financials": 0.02}
    sector_weights = {"Technology": 0.75, "Financials": 0.25}
    alloc, sel, inter, active, by_sector, methodology = calculate_brinson_attribution(
        positions,
        "USD",
        lambda _a, _b: 1.0,
        allow_mock=True,
        portfolio_sector_returns=sector_returns,
        portfolio_sector_weights=sector_weights,
        period_start=date(2024, 1, 1),
        period_end=date(2024, 12, 31),
    )
    assert by_sector
    assert alloc is not None
    assert active is not None
    assert "static benchmark" in methodology


def test_broker_sync_batch_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("app.db.state_store._data_dir", lambda: str(tmp_path))
    batch = create_broker_sync_batch(
        account_id="TEST-001",
        source="mock_flex_query",
        row_count=12,
        period_start=date(2024, 1, 1),
        period_end=date(2024, 12, 31),
    )
    loaded = read_broker_sync_batch("TEST-001", batch.batch_id)
    assert loaded is not None
    assert loaded.row_count == 12


def test_event_taxonomy_classifies_earnings_headline():
    event = classify_news_event("AAPL beats earnings expectations", "Revenue grew year over year")
    assert event.category == "earnings"
    assert event.sentiment == "positive"


def test_option_greeks_include_gamma_vega_rho():
    greeks = calculate_bs_greeks(100, 100, 30 / 365, 0.05, 0.25, "C")
    assert greeks["gamma"] > 0
    assert greeks["vega"] > 0
    assert "rho" in greeks
