from __future__ import annotations

from decimal import Decimal


def positive_decimal(value: Decimal | None, label: str, exclusions: list[str]) -> Decimal | None:
    if value is None or value <= 0:
        exclusions.append(f"{label}_unavailable")
        return None
    return value


def require_wacc_above_terminal_growth(wacc: Decimal, terminal_growth: Decimal, exclusions: list[str]) -> bool:
    if wacc <= terminal_growth:
        exclusions.append("wacc_must_exceed_terminal_growth")
        return False
    return True


def currencies_match(left: str, right: str, exclusions: list[str]) -> bool:
    if left.upper() != right.upper():
        exclusions.append("currency_mismatch")
        return False
    return True
