"""Process analytics over journal entries (plan §10.3).

Descriptive statistics about decision quality — NOT a prompt to trade more. Metrics
are withheld (null) rather than fabricated when there are too few closed entries.
"""

from __future__ import annotations

from statistics import mean
from typing import Any

from app.schemas.journal import JournalEntry

_MIN_SAMPLE = 3


def _closed(entries: list[JournalEntry]) -> list[JournalEntry]:
    return [e for e in entries if e.realized_return is not None]


def _group_mean(entries: list[JournalEntry], key) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[float]] = {}
    for e in entries:
        label = str(key(e) or "unspecified")
        groups.setdefault(label, []).append(float(e.realized_return))
    return {
        label: {"count": len(vals), "avg_return": round(mean(vals), 6)}
        for label, vals in groups.items()
    }


def compute_process_analytics(entries: list[JournalEntry]) -> dict[str, Any]:
    closed = _closed(entries)
    total_closed = len(closed)
    result: dict[str, Any] = {
        "entry_count": len(entries),
        "closed_count": total_closed,
        "sufficient_sample": total_closed >= _MIN_SAMPLE,
        "note": "Descriptive process metrics; not a recommendation to trade more.",
    }
    if total_closed < _MIN_SAMPLE:
        result["status"] = "insufficient_sample"
        result["metrics"] = None
        return result

    returns = [float(e.realized_return) for e in closed]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r < 0]
    avg_win = round(mean(wins), 6) if wins else None
    avg_loss = round(mean(losses), 6) if losses else None
    payoff = round(abs(avg_win / avg_loss), 4) if (avg_win and avg_loss) else None
    win_rate = round(len(wins) / total_closed, 4)
    loss_rate = round(len(losses) / total_closed, 4)
    expectancy = round(
        win_rate * (avg_win or 0.0) + loss_rate * (avg_loss or 0.0), 6
    )

    adherence_known = [e for e in closed if e.rule_adherence is not None]
    result["status"] = "available"
    result["metrics"] = {
        "win_rate": win_rate,
        "average_win": avg_win,
        "average_loss": avg_loss,
        "payoff_ratio": payoff,
        "expectancy": expectancy,
        "plan_adherence_rate": (
            round(sum(1 for e in adherence_known if e.rule_adherence) / len(adherence_known), 4)
            if adherence_known
            else None
        ),
        "unplanned_trade_count": sum(1 for e in closed if e.unplanned),
        "data_readiness_failure_count": sum(1 for e in closed if e.data_readiness_failure),
        "by_strategy": _group_mean(closed, lambda e: e.strategy),
        "by_market_regime": _group_mean(closed, lambda e: e.market_regime),
        "by_confidence": _group_mean(closed, lambda e: e.confidence),
        "by_outcome_classification": _group_mean(closed, lambda e: e.outcome_classification.value),
    }
    return result
