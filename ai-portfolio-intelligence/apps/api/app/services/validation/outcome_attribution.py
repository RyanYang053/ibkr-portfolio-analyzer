"""Decision outcome attribution — experimental forward windows."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def attribute_decision_outcome(
    *,
    decision_id: str,
    instrument_key: str,
    outcome: str,
    as_of: datetime | str,
    forward_returns: dict[int, float | None] | None = None,
    no_trade_baseline_returns: dict[int, float | None] | None = None,
) -> dict[str, Any]:
    """Label forward performance vs no-trade baseline. Numeric confidence stays withheld."""
    if isinstance(as_of, str):
        try:
            as_of_dt = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        except ValueError:
            as_of_dt = datetime.now(timezone.utc)
    else:
        as_of_dt = as_of if as_of.tzinfo else as_of.replace(tzinfo=timezone.utc)

    windows = (30, 90, 180, 365)
    forward_returns = forward_returns or {}
    no_trade_baseline_returns = no_trade_baseline_returns or {}
    series: list[dict[str, Any]] = []
    for days in windows:
        realized = forward_returns.get(days)
        baseline = no_trade_baseline_returns.get(days)
        differential = None
        if realized is not None and baseline is not None:
            differential = float(realized) - float(baseline)
        series.append(
            {
                "window_days": days,
                "due_at": (as_of_dt + timedelta(days=days)).isoformat(),
                "realized_return": realized,
                "no_trade_baseline_return": baseline,
                "differential_vs_no_trade": differential,
                "status": "observed" if realized is not None else "scheduled",
            }
        )
    return {
        "decision_id": decision_id,
        "instrument_key": instrument_key,
        "outcome": outcome,
        "as_of": as_of_dt.isoformat(),
        "windows": series,
        "methodology_status": "experimental",
        "confidence_status": "withheld",
        "order_generated": False,
        "notes": "Attribution is experimental. Do not treat differentials as calibrated edge.",
    }
