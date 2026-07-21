"""Walk-forward decision validation with point-in-time guards."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.product_contract import DecisionOutcome
from app.services.validation.point_in_time_guard import filter_usable_evidence


def walk_forward_splits(
    dates: list[str],
    *,
    train_size: int = 60,
    test_size: int = 20,
    step: int = 20,
) -> list[dict[str, Any]]:
    splits: list[dict[str, Any]] = []
    if train_size <= 0 or test_size <= 0 or step <= 0:
        return splits
    i = 0
    while i + train_size + test_size <= len(dates):
        train = dates[i : i + train_size]
        test = dates[i + train_size : i + train_size + test_size]
        splits.append(
            {
                "split_id": len(splits) + 1,
                "train_start": train[0],
                "train_end": train[-1],
                "test_start": test[0],
                "test_end": test[-1],
                "train_size": len(train),
                "test_size": len(test),
            }
        )
        i += step
    return splits


def evaluate_historical_decision(
    *,
    as_of: datetime,
    evidence: list[dict[str, Any]],
    methodology_version: str,
    policy_version: str,
    outcome: str | None = None,
) -> dict[str, Any]:
    """Replay a decision using only evidence available at as_of."""
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    usable, rejected = filter_usable_evidence(evidence, as_of=as_of)
    available = usable
    missing_critical = not any(
        e.get("evidence_type") in {"position_snapshot", "portfolio_risk_run", "fundamental_snapshot"}
        for e in available
    )
    resolved = outcome
    if missing_critical or rejected:
        if missing_critical:
            resolved = DecisionOutcome.DATA_INSUFFICIENT.value
    return {
        "as_of": as_of.isoformat(),
        "methodology_version": methodology_version,
        "policy_version": policy_version,
        "evidence_count": len(available),
        "excluded_future_count": len(rejected),
        "rejected": rejected[:20],
        "outcome": resolved or DecisionOutcome.MONITOR.value,
        "no_trade_baseline": True,
        "order_generated": False,
        "look_ahead_forbidden": True,
    }


def summarize_walk_forward(
    splits: list[dict[str, Any]],
    *,
    evaluations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    evaluations = evaluations or []
    outcome_counts: dict[str, int] = {}
    for item in evaluations:
        key = str(item.get("outcome") or "unknown")
        outcome_counts[key] = outcome_counts.get(key, 0) + 1
    return {
        "split_count": len(splits),
        "splits": splits,
        "evaluation_count": len(evaluations),
        "outcome_counts": outcome_counts,
        "status": "experimental" if evaluations else "splits_only",
        "methodology_status": "experimental",
        "order_generated": False,
        "metrics": {
            "decision_stability": None,
            "false_positive_review_rate": None,
            "no_trade_differential": None,
            "note": "Numeric calibration withheld until approved methodology fixtures exist.",
        },
    }
