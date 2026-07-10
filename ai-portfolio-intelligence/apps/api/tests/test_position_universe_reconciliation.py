from __future__ import annotations

from datetime import date

from app.schemas.domain import Position, utc_now
from app.services.portfolio.pnl_period_effects import compute_period_effects


def _position(symbol: str, qty: float, price: float, con_id: int) -> Position:
    return Position(
        account_id="TEST-001",
        symbol=symbol,
        company_name=symbol,
        asset_class="STK",
        quantity=qty,
        avg_cost=price,
        market_price=price,
        market_value=qty * price,
        unrealized_pnl=0,
        currency="USD",
        exchange="SMART",
        sector="Technology",
        industry="Software",
        portfolio_weight=5,
        stock_type="core",
        con_id=con_id,
        updated_at=utc_now(),
    )


def test_union_includes_opened_and_closed_positions():
    opening = [{"symbol": "AAA", "con_id": 1, "quantity": 10.0, "market_price": 100.0, "currency": "USD"}]
    closing = [
        _position("AAA", 10, 110, 1),
        _position("BBB", 5, 50, 2),
    ]
    effects = compute_period_effects(
        "TEST-001",
        date(2026, 1, 1),
        date(2026, 1, 31),
        opening,
        closing,
        "USD",
        lambda _a, _b, _c=None: 1.0,
    )
    assert "position_universe_change:BBB:2" in effects.exclusions
    assert effects.price_effect is not None


def test_missing_opening_market_price_withholds_price_effect():
    opening = [{"symbol": "AAA", "con_id": 1, "quantity": 10.0, "currency": "USD"}]
    closing = [_position("AAA", 10, 110, 1)]
    effects = compute_period_effects(
        "TEST-001",
        date(2026, 1, 1),
        date(2026, 1, 31),
        opening,
        closing,
        "USD",
        lambda _a, _b, _c=None: 1.0,
    )
    assert any("opening_market_price_missing" in item for item in effects.exclusions)
    assert effects.complete is False
