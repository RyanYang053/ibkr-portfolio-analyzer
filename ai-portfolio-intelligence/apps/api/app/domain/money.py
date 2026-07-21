"""Typed money values using Decimal."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any


class Money:
    """Currency-tagged Decimal amount for accounting and tax paths."""

    __slots__ = ("amount", "currency")

    def __init__(self, amount: Decimal | int | str | float, currency: str = "USD") -> None:
        if isinstance(amount, float):
            # Explicit conversion boundary — callers should prefer Decimal/str.
            amount = Decimal(str(amount))
        try:
            self.amount = Decimal(amount).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        except (InvalidOperation, TypeError) as exc:
            raise ValueError(f"Invalid money amount: {amount!r}") from exc
        currency_code = str(currency or "").strip().upper()
        if len(currency_code) != 3:
            raise ValueError(f"Invalid currency code: {currency!r}")
        self.currency = currency_code

    def __add__(self, other: Money) -> Money:
        self._same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, factor: Decimal | int | float) -> Money:
        if isinstance(factor, float):
            factor = Decimal(str(factor))
        return Money(self.amount * Decimal(factor), self.currency)

    def __truediv__(self, divisor: Decimal | int | float) -> Money:
        if isinstance(divisor, float):
            divisor = Decimal(str(divisor))
        return Money(self.amount / Decimal(divisor), self.currency)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        return self.currency == other.currency and self.amount == other.amount

    def __repr__(self) -> str:
        return f"Money({self.amount!s}, {self.currency!r})"

    def to_float(self) -> float:
        """Escape hatch for statistical models — prefer Decimal elsewhere."""
        return float(self.amount)

    def to_dict(self) -> dict[str, Any]:
        return {"amount": str(self.amount), "currency": self.currency}

    def _same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise ValueError(f"Currency mismatch: {self.currency} vs {other.currency}")
