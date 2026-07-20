"""Canada superficial-loss flags for tax decision-support (not filing)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal


@dataclass(frozen=True)
class SuperficialLossFlag:
    symbol: str
    loss_date: date
    window_start: date
    window_end: date
    reason: str
    status: str = "potential_adjustment"


def potential_repurchase_window_flags(
    *,
    symbol: str,
    disposal_date: date,
    disposal_quantity: Decimal,
    repurchase_dates: tuple[date, ...],
) -> tuple[SuperficialLossFlag, ...]:
    """Flag ±30 calendar-day repurchase windows as review items.

    This is a broad warning detector, not a CRA superficial-loss determination.
    Affiliated-person and substituted-property continuity checks are out of scope.
    """
    if disposal_quantity >= 0:
        return ()

    window_start = disposal_date - timedelta(days=30)
    window_end = disposal_date + timedelta(days=30)
    flags: list[SuperficialLossFlag] = []
    for repurchase in repurchase_dates:
        if window_start <= repurchase <= window_end:
            flags.append(
                SuperficialLossFlag(
                    symbol=symbol,
                    loss_date=disposal_date,
                    window_start=window_start,
                    window_end=window_end,
                    reason=(
                        f"Repurchase on {repurchase.isoformat()} falls within the "
                        "30-day repurchase warning window; review before treating the "
                        "loss as allowable."
                    ),
                )
            )
    return tuple(flags)


# Backward-compatible alias; prefer potential_repurchase_window_flags.
potential_superficial_loss_flags = potential_repurchase_window_flags
