"""Orchestrator applies point-in-time filtering before outcomes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.product_contract import EvidenceQuality
from app.schemas.decision_context import DecisionContext
from app.schemas.evidence import EvidenceRef
from app.services.decision_center.orchestrator import DecisionOrchestrator
from app.services.validation.point_in_time_guard import assert_point_in_time


def test_pit_guard_rejects_lookahead() -> None:
    as_of = datetime(2024, 1, 1, tzinfo=timezone.utc)
    check = assert_point_in_time(
        observed_at=as_of + timedelta(days=10),
        available_at=as_of + timedelta(days=10),
        as_of=as_of,
        field_name="future_price",
    )
    assert check["ok"] is False
    assert check["reason"] == "lookahead_leakage"


def test_orchestrator_survives_evidence_without_available_at() -> None:
    now = datetime.now(timezone.utc)
    context = DecisionContext(
        account_id="PIT",
        instrument_key="AAPL:1",
        symbol="AAPL",
        as_of=now,
        evidence_cutoff=now,
        data_quality={"status": "ok", "missing": []},
        thesis={"summary": "x"},
        risk={"max_drawdown_decimal": -0.1},
        valuation_status="withheld",
        tax={"status": "available"},
        liquidity={"status": "available"},
        fundamentals={"present": True},
        portfolio_fit={"over_concentrated": False, "weight": 5},
        methodology_versions={"decision_center_holding": "experimental"},
    )
    packet = DecisionOrchestrator().evaluate(context)
    assert packet.order_generated is False
    assert packet.outcome is not None


def test_evidence_ref_lookahead_fails_closed() -> None:
    as_of = datetime(2024, 6, 1, tzinfo=timezone.utc)
    future = as_of + timedelta(days=30)
    ref = EvidenceRef(
        evidence_id="ev_future",
        evidence_type="price",
        provider="test",
        observed_at=future,
        available_at=future,
        quality_status=EvidenceQuality.AVAILABLE,
        content_sha256="abc",
    )
    check = assert_point_in_time(
        observed_at=ref.observed_at,
        available_at=ref.available_at,
        as_of=as_of,
        field_name=ref.evidence_id,
    )
    assert check["fail_closed"] is True
    assert check["ok"] is False
