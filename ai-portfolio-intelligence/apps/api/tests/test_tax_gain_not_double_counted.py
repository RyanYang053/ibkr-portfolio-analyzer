from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services.portfolio.pnl_period_effects import compute_period_effects


def test_tax_realized_gain_not_in_price_effect():
    opening = [{"symbol": "MSFT", "con_id": 1, "quantity": 10.0, "local_price": 100.0, "currency": "USD", "multiplier": 1.0}]
    closing = [{"symbol": "MSFT", "con_id": 1, "quantity": 10.0, "local_price": 110.0, "currency": "USD", "multiplier": 1.0}]
    effects = compute_period_effects(
        "TEST-001",
        date(2026, 1, 1),
        date(2026, 1, 31),
        opening,
        closing,
        "USD",
        lambda *_: 1.0,
    )
    explained_mark = (effects.price_effect or Decimal("0")) + (effects.fx_effect or Decimal("0"))
    assert explained_mark == Decimal("100")
    if effects.tax_realized_gain is not None:
        assert effects.tax_realized_gain not in {effects.price_effect, effects.fx_effect}
