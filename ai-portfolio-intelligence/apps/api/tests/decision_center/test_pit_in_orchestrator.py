"""Orchestrator applies point-in-time filtering before outcomes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.product_contract import DecisionOutcome, EvidenceQuality
from app.schemas.decision_context import DecisionContext, EvaluationMode
from app.schemas.evidence import EvidenceRef
from app.services.decision_center.orchestrator import DecisionOrchestrator
from app.services.validation.point_in_time_guard import assert_point_in_time


def _pit_context(**overrides) -> DecisionContext:
    now = datetime.now(timezone.utc)
    base = dict(
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
    base.update(overrides)
    return DecisionContext(**base)


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
    # Live provisional mode (default) may recover from synthesized evidence lacking available_at.
    context = _pit_context()
    assert context.evaluation_mode == EvaluationMode.LIVE_PROVISIONAL
    packet = DecisionOrchestrator().evaluate(context)
    assert packet.order_generated is False
    assert packet.outcome is not None


def _lookahead_ref(as_of) -> EvidenceRef:
    future = as_of + timedelta(days=30)
    return EvidenceRef(
        evidence_id="ev_future",
        evidence_type="fundamental_snapshot",
        provider="test",
        observed_at=future,
        available_at=future,  # not available at as_of -> lookahead leakage
        quality_status=EvidenceQuality.AVAILABLE,
        content_sha256="abc",
    )


def test_orchestrator_replay_mode_fails_closed_on_lookahead_evidence() -> None:
    # P0.4: in historical replay, future-leaked evidence must fail the decision closed
    # (source integrity fails -> DATA_INSUFFICIENT), never proceed on a valid outcome.
    now = datetime.now(timezone.utc)
    context = _pit_context(
        as_of=now,
        evidence_cutoff=now,
        evaluation_mode=EvaluationMode.HISTORICAL_REPLAY,
        evidence=[_lookahead_ref(now)],
    )
    packet = DecisionOrchestrator().evaluate(context)
    assert context.source_integrity_ok is False
    assert packet.outcome == DecisionOutcome.DATA_INSUFFICIENT
    assert "source_integrity_failed" in packet.blockers
    assert packet.order_generated is False


def test_orchestrator_recovery_branch_is_mode_gated() -> None:
    # P0.4: the fail-open recovery (restore evidence + reset source integrity) is gated
    # to live mode. In replay, an all-missing-available_at wipe stays failed closed.
    now = datetime.now(timezone.utc)
    wiped = [{"evidence_id": "d1", "evidence_type": "news", "observed_at": now.isoformat()}]
    context = _pit_context(
        as_of=now, evidence_cutoff=now, evaluation_mode=EvaluationMode.HISTORICAL_REPLAY, evidence=wiped
    )
    packet = DecisionOrchestrator().evaluate(context)
    assert context.source_integrity_ok is False
    assert packet.outcome == DecisionOutcome.DATA_INSUFFICIENT


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
