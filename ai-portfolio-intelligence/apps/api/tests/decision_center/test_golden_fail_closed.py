"""Golden financial edge-case fixtures for Decision OS fail-closed behavior."""

from __future__ import annotations

from app.services.decision_center.holding_context import HoldingContext
from app.services.decision_center.holding_decision import evaluate_holding_decision


def test_missing_fundamentals_never_become_zero_add() -> None:
    decision = evaluate_holding_decision(
        HoldingContext(
            instrument_key="MISS:1",
            symbol="MISS",
            account_id="GOLDEN",
            data_quality={"status": "incomplete", "missing": ["fundamentals"]},
            thesis={"summary": "x"},
            risk={"max_drawdown_decimal": -0.1},
            valuation_status="approved",
            portfolio_fit={"over_concentrated": False},
            lens_ensemble={"synthesis_labels": ["quality_supportive"]},
        )
    )
    assert decision["outcome"] == "data_insufficient"
    assert decision["order_generated"] is False


def test_stale_option_quote_does_not_approve_implementation() -> None:
    decision = evaluate_holding_decision(
        HoldingContext(
            instrument_key="OPT:1",
            symbol="OPT",
            account_id="GOLDEN",
            data_quality={"status": "ok", "missing": [], "stale": ["option_quote"]},
            thesis={"summary": "covered call book"},
            risk={"max_drawdown_decimal": -0.05},
            valuation_status="available",
            portfolio_fit={"over_concentrated": False},
            lens_ensemble={},
            tax_flags={"status": "provisional"},
        )
    )
    assert decision["outcome"] == "data_insufficient"
    assert decision["order_generated"] is False


def test_hard_concentration_triggers_trim_without_valuation() -> None:
    decision = evaluate_holding_decision(
        HoldingContext(
            instrument_key="CONC:1",
            symbol="CONC",
            account_id="GOLDEN",
            data_quality={"status": "ok", "missing": []},
            thesis={"summary": "too big"},
            risk={"max_drawdown_decimal": -0.1},
            valuation_status="withheld",
            portfolio_fit={"over_concentrated": True, "weight": 25.0},
            lens_ensemble={},
            tax_flags={"status": "available"},
        )
    )
    assert decision["outcome"] == "review_trim"
    assert decision["action"] == "Review trim"
    assert decision["order_generated"] is False
