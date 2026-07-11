from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.schemas.domain import Transaction
from app.services.portfolio.signed_inventory_engine import compute_signed_inventory_trade_timing


def _txn(action: str, quantity: float, price: float) -> Transaction:
    return Transaction(
        account_id="A",
        symbol="TEST",
        trade_date=date(2026, 1, 15),
        action=action,
        quantity=quantity,
        price=price,
        commission=0,
        currency="USD",
        source="test",
    )


def test_long_to_short_reversal_timing_effect():
    timing, final_inventory, _, complete = compute_signed_inventory_trade_timing(
        Decimal("10"),
        [_txn("sell", 15, 105)],
        open_price=Decimal("100"),
        close_price=Decimal("110"),
        open_fx=Decimal("1"),
        close_fx=Decimal("1"),
        multiplier=Decimal("1"),
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        currency="USD",
        base_currency="USD",
        fx_resolver=lambda *_: 1.0,
    )
    assert complete
    assert timing == Decimal("25")
    assert final_inventory == Decimal("-5")


def test_partial_short_cover_timing_effect():
    timing, final_inventory, _, complete = compute_signed_inventory_trade_timing(
        Decimal("-10"),
        [_txn("buy", 5, 95)],
        open_price=Decimal("100"),
        close_price=Decimal("90"),
        open_fx=Decimal("1"),
        close_fx=Decimal("1"),
        multiplier=Decimal("1"),
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        currency="USD",
        base_currency="USD",
        fx_resolver=lambda *_: 1.0,
    )
    assert complete
    assert timing == Decimal("25")
    assert final_inventory == Decimal("-5")
