"""Outcome precedence unit tests."""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.product_contract import DecisionOutcome
from app.schemas.decision_context import DecisionContext
from app.schemas.decision_gate import GateResult
from app.services.decision_center.outcome_precedence import resolve_outcome


def _ctx(**kwargs) -> DecisionContext:
    now = datetime.now(timezone.utc)
    base = dict(
        account_id="acct",
        instrument_key="AAPL:1",
        symbol="AAPL",
        as_of=now,
        evidence_cutoff=now,
        position={"portfolio_weight": 5.0},
        thesis_status="active",
        hard_risk_breach=False,
        hard_policy_breach=False,
        valuation_status="approved",
        supportive_quality_evidence=False,
        add_capacity_available=False,
        lens_ensemble={},
    )
    base.update(kwargs)
    return DecisionContext(**base)


def test_data_quality_failure_is_data_insufficient() -> None:
    gates = [GateResult(gate_id="data_quality", passed=False, terminal=True)]
    assert resolve_outcome(gates, _ctx()) == DecisionOutcome.DATA_INSUFFICIENT


def test_hard_risk_breach_is_review_trim() -> None:
    assert resolve_outcome([], _ctx(hard_risk_breach=True)) == DecisionOutcome.REVIEW_TRIM


def test_supportive_and_valuation_can_review_add() -> None:
    outcome = resolve_outcome(
        [],
        _ctx(
            supportive_quality_evidence=True,
            valuation_status="approved",
            add_capacity_available=True,
        ),
    )
    assert outcome == DecisionOutcome.REVIEW_ADD


def test_default_is_monitor() -> None:
    assert resolve_outcome([], _ctx()) == DecisionOutcome.MONITOR
