"""Fail-closed gate contracts for tax, methodology, and implementation."""

from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.decision_context import DecisionContext
from app.services.decision_center.gates.remaining import (
    ImplementationGate,
    MethodologyGate,
    TaxGate,
)
from app.services.decision_center.ai_outcome_enforcement import enforce_authoritative_outcome
from app.core.product_contract import DecisionOutcome


def _ctx(**kwargs) -> DecisionContext:
    now = datetime.now(timezone.utc)
    base = dict(
        account_id="T",
        instrument_key="AAPL:1",
        symbol="AAPL",
        as_of=now,
        evidence_cutoff=now,
    )
    base.update(kwargs)
    return DecisionContext(**base)


def test_tax_gate_fails_on_unknown() -> None:
    result = TaxGate().evaluate(_ctx(tax={"status": "unknown"}))
    assert result.passed is False
    assert "tax_inputs_incomplete" in result.blockers


def test_tax_gate_fails_when_missing() -> None:
    result = TaxGate().evaluate(_ctx(tax={}))
    assert result.passed is False


def test_methodology_gate_fails_when_unbound() -> None:
    result = MethodologyGate().evaluate(_ctx(methodology_versions={}))
    assert result.passed is False
    assert "methodology_unbound" in result.blockers


def test_implementation_ready_true_only_when_inputs_ok() -> None:
    result = ImplementationGate().evaluate(
        _ctx(
            tax={"status": "available"},
            liquidity={"status": "ok"},
            valuation_status="approved_for_personal_use",
        )
    )
    assert result.passed is True
    assert result.details.get("implementation_ready") is True


def test_ai_enforcement_overwrites_forbidden_action_labels() -> None:
    enforced = enforce_authoritative_outcome(
        {
            "action": "Strong Add",
            "rule_engine_action": "Buy",
            "summary": "Strong Add now",
            "order_generated": True,
        },
        decision_id="dec_1",
        outcome=DecisionOutcome.MONITOR,
    )
    assert enforced["action"] == "No action"
    assert enforced["rule_engine_action"] == "No action"
    assert enforced["authoritative_outcome"] == "monitor"
    assert enforced["order_generated"] is False
    assert "Strong Add" not in str(enforced.get("summary") or "")
