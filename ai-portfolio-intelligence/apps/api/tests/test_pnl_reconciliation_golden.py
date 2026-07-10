from __future__ import annotations

from datetime import date

from app.schemas.domain import Position, utc_now
from app.services.portfolio.pnl_period_effects import compute_period_price_and_realized_effects


def test_golden_hold_through_period_price_effect():
    opening = [{"symbol": "MSFT", "con_id": 1, "quantity": 10.0, "market_price": 100.0, "currency": "USD"}]
    closing = [
        Position(
            account_id="TEST-001",
            symbol="MSFT",
            company_name="MSFT",
            asset_class="STK",
            quantity=10,
            avg_cost=90,
            market_price=110,
            market_value=1100,
            unrealized_pnl=200,
            currency="USD",
            exchange="NASDAQ",
            sector="Technology",
            industry="Software",
            portfolio_weight=10,
            stock_type="mega_cap_quality",
            con_id=1,
            updated_at=utc_now(),
        )
    ]
    price_effect, realized, fx_effect, exclusions = compute_period_price_and_realized_effects(
        "TEST-001",
        date(2026, 1, 1),
        date(2026, 1, 31),
        opening,
        closing,
        "USD",
        lambda _a, _b, _c=None: 1.0,
    )
    assert price_effect == 100.0
    assert fx_effect == 0.0
    assert "opening_positions_unavailable" not in exclusions


def test_missing_opening_snapshot_withholds_combined_mark_effect():
    price_effect, realized, fx_effect, exclusions = compute_period_price_and_realized_effects(
        "TEST-001",
        date(2026, 1, 1),
        date(2026, 1, 31),
        [],
        [],
        "USD",
        lambda _a, _b, _c=None: 1.0,
    )
    assert price_effect is None
    assert "opening_positions_unavailable" in exclusions
