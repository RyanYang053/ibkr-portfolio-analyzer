"""Walk-forward and PIT validation tests."""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.validation.point_in_time_guard import (
    assert_point_in_time,
    filter_usable_evidence,
    is_stale,
    stale_evidence_ids,
)
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


def test_replay_fails_closed_when_any_evidence_rejected_even_with_critical_present() -> None:
    # P0.4: a leaked/future item must NOT be silently excluded while a valid outcome
    # proceeds. Present critical evidence + one rejected future item => DATA_INSUFFICIENT.
    as_of = datetime(2024, 6, 1, tzinfo=timezone.utc)
    result = evaluate_historical_decision(
        as_of=as_of,
        evidence=[
            {
                "evidence_id": "ok_fund",
                "evidence_type": "fundamental_snapshot",
                "available_at": "2024-05-01T00:00:00+00:00",
                "observed_at": "2024-05-01T00:00:00+00:00",
            },
            {
                "evidence_id": "future_news",
                "evidence_type": "news",
                "available_at": "2024-07-01T00:00:00+00:00",
                "observed_at": "2024-07-01T00:00:00+00:00",
            },
        ],
        methodology_version="v1",
        policy_version="p1",
        outcome="review_add",
    )
    assert result["outcome"] == "data_insufficient"
    assert result["fail_closed"] is True
    assert "point_in_time_rejection" in result["replay_blocked_reasons"]


def test_replay_fails_closed_on_unknown_methodology_version() -> None:
    as_of = datetime(2024, 6, 1, tzinfo=timezone.utc)
    result = evaluate_historical_decision(
        as_of=as_of,
        evidence=[
            {
                "evidence_id": "ok_fund",
                "evidence_type": "fundamental_snapshot",
                "available_at": "2024-05-01T00:00:00+00:00",
                "observed_at": "2024-05-01T00:00:00+00:00",
            }
        ],
        methodology_version="unknown",
        policy_version="p1",
        outcome="monitor",
    )
    assert result["outcome"] == "data_insufficient"
    assert "unknown_methodology_version" in result["replay_blocked_reasons"]


def test_replay_fails_closed_on_incomplete_corporate_actions() -> None:
    result = evaluate_historical_decision(
        as_of=datetime(2024, 6, 1, tzinfo=timezone.utc),
        evidence=[{"evidence_id": "f", "evidence_type": "fundamental_snapshot", "available_at": "2024-05-01T00:00:00+00:00"}],
        methodology_version="v1",
        policy_version="p1",
        outcome="monitor",
        corporate_actions_complete=False,
    )
    assert result["outcome"] == "data_insufficient"
    assert "corporate_action_adjustment_incomplete" in result["replay_blocked_reasons"]


def test_replay_fails_closed_on_missing_required_source() -> None:
    result = evaluate_historical_decision(
        as_of=datetime(2024, 6, 1, tzinfo=timezone.utc),
        evidence=[{"evidence_id": "f", "evidence_type": "fundamental_snapshot", "available_at": "2024-05-01T00:00:00+00:00"}],
        methodology_version="v1",
        policy_version="p1",
        outcome="monitor",
        required_evidence_types=("position_snapshot", "portfolio_risk_run"),
    )
    assert result["outcome"] == "data_insufficient"
    assert any("missing_required_sources" in r for r in result["replay_blocked_reasons"])


def test_live_staleness_is_flagged_not_rejected() -> None:
    as_of = "2024-06-01T00:00:00+00:00"
    records = [
        {"evidence_id": "fresh", "available_at": "2024-05-01T00:00:00+00:00", "stale_after": "2024-07-01T00:00:00+00:00"},
        {"evidence_id": "stale", "available_at": "2024-01-01T00:00:00+00:00", "stale_after": "2024-03-01T00:00:00+00:00"},
    ]
    assert is_stale(records[1], as_of) is True
    assert is_stale(records[0], as_of) is False
    usable, rejected = filter_usable_evidence(records, as_of=as_of)
    # Both are point-in-time usable (available before as_of); staleness only flags.
    assert len(usable) == 2 and rejected == []
    assert stale_evidence_ids(usable) == ["stale"]


def test_walk_forward_splits_and_summary() -> None:
    dates = [f"2024-01-{i:02d}" for i in range(1, 29)] + [f"2024-02-{i:02d}" for i in range(1, 29)]
    # Need enough dates for train 60 + test 20
    dates = [f"2024-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}" for i in range(120)]
    splits = walk_forward_splits(dates, train_size=60, test_size=20, step=20)
    summary = summarize_walk_forward(splits, evaluations=[{"outcome": "monitor"}])
    assert summary["split_count"] >= 1
    assert summary["order_generated"] is False
