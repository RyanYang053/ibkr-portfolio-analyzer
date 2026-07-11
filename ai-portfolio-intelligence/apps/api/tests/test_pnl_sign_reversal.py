from __future__ import annotations

from datetime import date

from app.schemas.domain import Transaction
from app.services.portfolio.pnl_decomposition import _signed_notional, _convert_amount


def test_dividend_reversal_reduces_income():
    reversal = Transaction(
        account_id="A",
        symbol="MSFT",
        trade_date=date(2026, 1, 10),
        action="dividend_reversal",
        quantity=0,
        price=0,
        amount=-50.0,
        commission=0,
        currency="USD",
        source="test",
    )
    assert _signed_notional(reversal) == -50.0


def test_withholding_tax_reversal():
    reversal = Transaction(
        account_id="A",
        symbol="MSFT",
        trade_date=date(2026, 1, 10),
        action="withholding_tax_reversal",
        quantity=0,
        price=0,
        amount=7.5,
        commission=0,
        currency="USD",
        source="test",
    )
    converted = _convert_amount(_signed_notional(reversal), "USD", "USD", date(2026, 1, 10), lambda *_: 1.0)
    assert converted == 7.5
