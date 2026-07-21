"""Unit boundary contracts for money and ratios."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.money import Money
from app.domain.units import BasisPoints, Percent, Ratio


def test_money_rejects_currency_mismatch() -> None:
    a = Money("10.00", "USD")
    b = Money("1.00", "CAD")
    with pytest.raises(ValueError):
        _ = a + b


def test_percent_ratio_bps_conversion() -> None:
    assert Percent("12.5").as_ratio().value == Decimal("0.125")
    assert Ratio("0.01").as_percent().value == Decimal("1")
    assert BasisPoints(25).as_ratio().value == Decimal("0.0025")
