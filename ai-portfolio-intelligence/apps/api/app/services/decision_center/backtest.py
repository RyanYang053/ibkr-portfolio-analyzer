"""Point-in-time integrity helpers for historically evaluated signals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class PointInTimeDecisionRecord:
    as_of: date
    instrument_key: str
    outcome: str
    data_complete: bool
    look_ahead_used: bool = False


def assert_no_look_ahead(records: tuple[PointInTimeDecisionRecord, ...]) -> None:
    bad = [r for r in records if r.look_ahead_used]
    if bad:
        raise AssertionError(
            "Decision validation must remain point-in-time; look-ahead detected for "
            + ", ".join(f"{r.instrument_key}@{r.as_of.isoformat()}" for r in bad)
        )


def historically_evaluated_label() -> str:
    """Public label for personal backtests — never 'validated investment advice'."""
    return "historically evaluated"
