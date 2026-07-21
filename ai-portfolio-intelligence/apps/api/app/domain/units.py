"""Typed percent / ratio / basis-point helpers."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation


class Percent:
    """Human-facing percent (e.g. 12.5 means 12.5%)."""

    __slots__ = ("value",)

    def __init__(self, value: Decimal | int | str | float) -> None:
        self.value = _to_decimal(value)

    def as_ratio(self) -> Ratio:
        return Ratio(self.value / Decimal("100"))

    def __float__(self) -> float:
        return float(self.value)

    def __repr__(self) -> str:
        return f"Percent({self.value!s})"


class Ratio:
    """Unit interval / decimal fraction (e.g. 0.125 means 12.5%)."""

    __slots__ = ("value",)

    def __init__(self, value: Decimal | int | str | float) -> None:
        self.value = _to_decimal(value)

    def as_percent(self) -> Percent:
        return Percent(self.value * Decimal("100"))

    def __float__(self) -> float:
        return float(self.value)

    def __repr__(self) -> str:
        return f"Ratio({self.value!s})"


class BasisPoints:
    """Basis points (100 bps = 1%)."""

    __slots__ = ("value",)

    def __init__(self, value: Decimal | int | str | float) -> None:
        self.value = _to_decimal(value)

    def as_ratio(self) -> Ratio:
        return Ratio(self.value / Decimal("10000"))

    def __float__(self) -> float:
        return float(self.value)

    def __repr__(self) -> str:
        return f"BasisPoints({self.value!s})"


def _to_decimal(value: Decimal | int | str | float) -> Decimal:
    if isinstance(value, float):
        value = Decimal(str(value))
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"Invalid numeric unit: {value!r}") from exc
