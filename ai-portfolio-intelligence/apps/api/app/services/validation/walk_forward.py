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
    corporate_actions_complete: bool = True,
    required_evidence_types: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Replay a decision using only evidence available at as_of.

    Fails closed (plan §15.4) on every replay condition: missing availability or
    future leakage, missing critical evidence, an explicit required source missing,
    incomplete corporate-action adjustment, or an unknown methodology version.
    """
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    usable, rejected = filter_usable_evidence(evidence, as_of=as_of)
    available = usable
    available_types = {e.get("evidence_type") for e in available}
    missing_critical = not (
        available_types & {"position_snapshot", "portfolio_risk_run", "fundamental_snapshot"}
    )

    replay_blocked_reasons: list[str] = []
    if rejected:
        replay_blocked_reasons.append("point_in_time_rejection")
    if missing_critical:
        replay_blocked_reasons.append("missing_critical_evidence")
    if required_evidence_types:
        missing_required = [t for t in required_evidence_types if t not in available_types]
        if missing_required:
            replay_blocked_reasons.append(f"missing_required_sources:{','.join(missing_required)}")
    if not corporate_actions_complete:
        replay_blocked_reasons.append("corporate_action_adjustment_incomplete")
    if not methodology_version or str(methodology_version).strip().lower() in {"", "unknown"}:
        replay_blocked_reasons.append("unknown_methodology_version")
    resolved = outcome
    if replay_blocked_reasons:
        resolved = DecisionOutcome.DATA_INSUFFICIENT.value
    return {
        "as_of": as_of.isoformat(),
        "methodology_version": methodology_version,
        "policy_version": policy_version,
        "evidence_count": len(available),
        "excluded_future_count": len(rejected),
        "rejected": rejected[:20],
        "outcome": resolved or DecisionOutcome.MONITOR.value,
        "replay_blocked_reasons": replay_blocked_reasons,
        "fail_closed": bool(replay_blocked_reasons),
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
