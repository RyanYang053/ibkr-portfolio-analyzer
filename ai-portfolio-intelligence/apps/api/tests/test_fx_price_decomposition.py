from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.schemas.domain import Position, utc_now
from app.services.portfolio.pnl_period_effects import compute_period_effects


def _position(symbol: str, *, qty: float, price: float, currency: str = "USD", con_id: int = 1) -> Position:
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
        currency=currency,
        exchange="SMART",
        sector="Technology",
        industry="Software",
        portfolio_weight=5,
        stock_type="core",
        con_id=con_id,
        updated_at=utc_now(),
    )


def test_fx_only_move_with_constant_local_price():
    opening = [{"symbol": "RY", "con_id": 1, "quantity": 100.0, "market_price": 100.0, "currency": "CAD"}]
    closing = [_position("RY", qty=100, price=100.0, currency="CAD")]
    effects = compute_period_effects(
        "TEST-001",
        date(2026, 1, 1),
        date(2026, 1, 31),
        opening,
        closing,
        "USD",
        lambda _from, _to, as_of: 0.70 if as_of == date(2026, 1, 1) else 0.75,
    )
    assert effects.price_effect == Decimal("0")
    assert effects.fx_effect == Decimal("500")
    assert effects.price_fx_cross_effect == Decimal("0")


def test_price_only_move_with_constant_fx():
    opening = [{"symbol": "RY", "con_id": 1, "quantity": 100.0, "market_price": 100.0, "currency": "CAD"}]
    closing = [_position("RY", qty=100, price=110.0, currency="CAD")]
    effects = compute_period_effects(
        "TEST-001",
        date(2026, 1, 1),
        date(2026, 1, 31),
        opening,
        closing,
        "USD",
        lambda _from, _to, _as_of: 0.75,
    )
    assert effects.price_effect == Decimal("750")
    assert effects.fx_effect == Decimal("0")
    assert effects.price_fx_cross_effect == Decimal("0")


def test_simultaneous_price_and_fx_move_splits_cross_term():
    opening = [{"symbol": "RY", "con_id": 1, "quantity": 10.0, "market_price": 100.0, "currency": "CAD"}]
    closing = [_position("RY", qty=10, price=110.0, currency="CAD")]
    effects = compute_period_effects(
        "TEST-001",
        date(2026, 1, 1),
        date(2026, 1, 31),
        opening,
        closing,
        "USD",
        lambda _from, _to, as_of: 0.70 if as_of == date(2026, 1, 1) else 0.75,
    )
    assert effects.price_effect == Decimal("70")
    assert effects.fx_effect == Decimal("50")
    assert effects.price_fx_cross_effect == Decimal("5")
