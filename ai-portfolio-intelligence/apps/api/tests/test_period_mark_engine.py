from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.schemas.domain import Transaction
from app.services.portfolio.period_mark_engine import _matched_signed_quantity, trade_timing_effect


def test_matched_signed_quantity_long():
    assert _matched_signed_quantity(Decimal("10"), Decimal("8")) == Decimal("8")


def test_matched_signed_quantity_short():
    assert _matched_signed_quantity(Decimal("-10"), Decimal("-6")) == Decimal("-6")


def test_matched_signed_quantity_sign_mismatch():
    assert _matched_signed_quantity(Decimal("10"), Decimal("-5")) == Decimal("0")


def test_trade_timing_buy():
    txn = Transaction(
        account_id="A",
        symbol="MSFT",
        trade_date=date(2026, 1, 15),
        action="buy",
        quantity=5,
        price=100,
        commission=0,
        currency="USD",
        source="test",
    )
    effect = trade_timing_effect(
        txn,
        opening_price=Decimal("95"),
        closing_price=Decimal("110"),
        trade_fx=Decimal("1"),
        closing_fx=Decimal("1"),
        multiplier=Decimal("1"),
    )
    assert effect == Decimal("50")
