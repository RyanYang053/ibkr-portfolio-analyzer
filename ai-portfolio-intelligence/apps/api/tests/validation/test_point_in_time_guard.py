"""Point-in-time guard tests."""

from __future__ import annotations

from app.services.validation.point_in_time_guard import assert_point_in_time, filter_usable_evidence


def test_rejects_lookahead() -> None:
    result = assert_point_in_time(
        observed_at="2024-01-02T00:00:00+00:00",
        available_at="2024-01-10T00:00:00+00:00",
        as_of="2024-01-05T00:00:00+00:00",
        field_name="eps",
    )
    assert result["ok"] is False
    assert result["reason"] == "lookahead_leakage"
    assert result["fail_closed"] is True


def test_accepts_available_before_as_of() -> None:
    result = assert_point_in_time(
        observed_at="2024-01-02T00:00:00+00:00",
        available_at="2024-01-03T00:00:00+00:00",
        as_of="2024-01-05T00:00:00+00:00",
    )
    assert result["ok"] is True


def test_filter_usable_evidence() -> None:
    usable, rejected = filter_usable_evidence(
        [
            {
                "evidence_id": "e1",
                "available_at": "2024-01-01T00:00:00+00:00",
                "observed_at": "2024-01-01T00:00:00+00:00",
            },
            {
                "evidence_id": "e2",
                "available_at": "2024-02-01T00:00:00+00:00",
                "observed_at": "2024-02-01T00:00:00+00:00",
            },
        ],
        as_of="2024-01-15T00:00:00+00:00",
    )
    assert len(usable) == 1
    assert usable[0]["evidence_id"] == "e1"
    assert len(rejected) == 1
