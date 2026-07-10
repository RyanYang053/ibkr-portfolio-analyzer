from __future__ import annotations

from app.schemas.domain import Position, utc_now
from app.services.portfolio_construction.optimizer import _instrument_key


def test_duplicate_symbol_different_con_id_produces_distinct_keys():
    base = dict(
        account_id="MOCK-001",
        company_name="Test",
        asset_class="STK",
        quantity=10,
        avg_cost=100,
        market_price=110,
        market_value=1100,
        unrealized_pnl=100,
        currency="USD",
        exchange="SMART",
        sector="Technology",
        industry="Software",
        portfolio_weight=5,
        stock_type="core",
        updated_at=utc_now(),
    )
    first = Position(symbol="ABC", con_id=1, **base)
    second = Position(symbol="ABC", con_id=2, **base)
    assert _instrument_key(first) != _instrument_key(second)
