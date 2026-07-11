from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.schemas.domain import Transaction, utc_now
from app.services.portfolio.period_mark_engine import trade_timing_effect


def test_sell_trade_timing_effect():
    txn = Transaction(
        account_id="A",
        symbol="AAPL",
        trade_date=date(2026, 1, 15),
        action="sell",
        quantity=10,
        price=200,
        commission=1,
        currency="USD",
        source="test",
    )
    effect = trade_timing_effect(
        txn,
        opening_price=Decimal("180"),
        closing_price=Decimal("190"),
        trade_fx=Decimal("1"),
        closing_fx=Decimal("1"),
        multiplier=Decimal("1"),
    )
    assert effect == Decimal("200")
