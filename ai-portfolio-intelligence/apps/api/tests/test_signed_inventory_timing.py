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


def test_split_updates_signed_inventory():
    split = Transaction(
        account_id="A",
        symbol="TEST",
        trade_date=date(2026, 1, 10),
        action="corporate_action",
        quantity=0,
        price=0,
        commission=0,
        currency="USD",
        source="test",
        description="2 for 1 stock split",
    )

    timing, final_inventory, exclusions, complete = (
        compute_signed_inventory_trade_timing(
            Decimal("10"),
            [split],
            open_price=Decimal("100"),
            close_price=Decimal("50"),
            open_fx=Decimal("1"),
            close_fx=Decimal("1"),
            multiplier=Decimal("1"),
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            currency="USD",
            base_currency="USD",
            fx_resolver=lambda *_: 1.0,
        )
    )

    assert final_inventory == Decimal("20")
    assert complete is True
    assert timing == Decimal("0")
    assert any(
        item.startswith("corporate_action_price_normalized:TEST")
        for item in exclusions
    )


def test_split_then_sell_uses_normalized_open_mark():
    split = Transaction(
        account_id="A",
        symbol="TEST",
        trade_date=date(2026, 1, 10),
        action="corporate_action",
        quantity=0,
        price=0,
        commission=0,
        currency="USD",
        source="test",
        description="2 for 1 stock split",
    )
    sell = Transaction(
        account_id="A",
        symbol="TEST",
        trade_date=date(2026, 1, 20),
        action="sell",
        quantity=10,
        price=55,
        commission=0,
        currency="USD",
        source="test",
    )

    timing, final_inventory, _, complete = compute_signed_inventory_trade_timing(
        Decimal("10"),
        [split, sell],
        open_price=Decimal("100"),
        close_price=Decimal("50"),
        open_fx=Decimal("1"),
        close_fx=Decimal("1"),
        multiplier=Decimal("1"),
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        currency="USD",
        base_currency="USD",
        fx_resolver=lambda *_: 1.0,
    )

    # Open mark normalized to 50; sell at 55 on 10 post-split shares => +50 timing.
    assert complete is True
    assert final_inventory == Decimal("10")
    assert timing == Decimal("50")
