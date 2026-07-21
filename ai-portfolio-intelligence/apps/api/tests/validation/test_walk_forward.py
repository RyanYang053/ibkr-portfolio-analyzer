"""Walk-forward and PIT validation tests."""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.validation.point_in_time_guard import assert_point_in_time, filter_usable_evidence
from app.services.validation.walk_forward import (
    evaluate_historical_decision,
    summarize_walk_forward,
    walk_forward_splits,
)


def test_point_in_time_rejects_lookahead() -> None:
    result = assert_point_in_time(
        observed_at="2024-06-02T00:00:00+00:00",
        available_at="2024-06-02T00:00:00+00:00",
        as_of="2024-06-01T00:00:00+00:00",
        field_name="price",
    )
    assert result["ok"] is False
    assert result["reason"] == "lookahead_leakage"


def test_filter_usable_evidence() -> None:
    usable, rejected = filter_usable_evidence(
        [
            {
                "evidence_id": "ok",
                "available_at": "2024-01-01T00:00:00+00:00",
                "observed_at": "2024-01-01T00:00:00+00:00",
            },
            {
                "evidence_id": "future",
                "available_at": "2025-01-01T00:00:00+00:00",
                "observed_at": "2025-01-01T00:00:00+00:00",
            },
        ],
        as_of="2024-06-01T00:00:00+00:00",
    )
    assert len(usable) == 1
    assert len(rejected) == 1


def test_walk_forward_evaluate_fail_closed() -> None:
    as_of = datetime(2024, 6, 1, tzinfo=timezone.utc)
    result = evaluate_historical_decision(
        as_of=as_of,
        evidence=[
            {
                "evidence_id": "future_fund",
                "evidence_type": "fundamental_snapshot",
                "available_at": "2024-07-01T00:00:00+00:00",
                "observed_at": "2024-07-01T00:00:00+00:00",
            }
        ],
        methodology_version="v1",
        policy_version="p1",
        outcome="review_add",
    )
    assert result["outcome"] == "data_insufficient"
    assert result["order_generated"] is False
    assert result["excluded_future_count"] == 1


def test_walk_forward_splits_and_summary() -> None:
    dates = [f"2024-01-{i:02d}" for i in range(1, 29)] + [f"2024-02-{i:02d}" for i in range(1, 29)]
    # Need enough dates for train 60 + test 20
    dates = [f"2024-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}" for i in range(120)]
    splits = walk_forward_splits(dates, train_size=60, test_size=20, step=20)
    summary = summarize_walk_forward(splits, evaluations=[{"outcome": "monitor"}])
    assert summary["split_count"] >= 1
    assert summary["order_generated"] is False
