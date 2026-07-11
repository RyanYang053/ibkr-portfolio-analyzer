from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services.portfolio.pnl_period_effects import compute_period_effects


def test_short_position_price_effect():
    opening = [{"symbol": "SPY", "con_id": 1, "quantity": -10.0, "local_price": 500.0, "currency": "USD", "multiplier": 1.0}]
    closing = [
        {
            "symbol": "SPY",
            "con_id": 1,
            "quantity": -10.0,
            "local_price": 480.0,
            "currency": "USD",
            "multiplier": 1.0,
        }
    ]
    effects = compute_period_effects(
        "TEST",
        date(2026, 1, 1),
        date(2026, 1, 31),
        opening,
        closing,
        "USD",
        lambda *_: 1.0,
    )
    assert effects.price_effect is not None
    assert effects.price_effect == Decimal("200")
