from app.services.decision_center.decision_validation import (
    DecisionOutcome,
    to_personal_decision_support,
)
from app.services.decision_center.holding_context import HoldingContext
from app.services.decision_center.holding_decision import evaluate_holding_decision


def supported_scenarios() -> list[HoldingContext]:
    return [
        HoldingContext(
            instrument_key="AAPL",
            symbol="AAPL",
            account_id="U0001",
            data_quality={"status": "ok", "missing": []},
            thesis={"summary": "Quality compounder"},
            risk={"max_drawdown_decimal": -0.12},
            valuation_status="available",
            portfolio_fit={"over_concentrated": False},
            lens_ensemble={"synthesis_labels": ["quality_supportive"]},
        ),
        HoldingContext(
            instrument_key="XYZ",
            symbol="XYZ",
            account_id="U0001",
            data_quality={"status": "ok", "missing": []},
            thesis={},
            risk={},
            valuation_status="missing",
            portfolio_fit={},
            lens_ensemble={},
        ),
    ]


def test_available_but_unapproved_valuation_never_returns_review_add():
    context = HoldingContext(
        instrument_key="AAPL",
        symbol="AAPL",
        account_id="U0001",
        data_quality={"status": "ok", "missing": []},
        thesis={"summary": "Quality compounder"},
        risk={"max_drawdown_decimal": -0.12},
        valuation_status="available",
        portfolio_fit={"over_concentrated": False},
        lens_ensemble={"synthesis_labels": ["quality_supportive"]},
    )
    decision = evaluate_holding_decision(context)
    assert decision["action"] != "Review add"
    assert decision["outcome"] != "review_add"


def test_approved_valuation_can_return_review_add():
    context = HoldingContext(
        instrument_key="AAPL",
        symbol="AAPL",
        account_id="U0001",
        data_quality={"status": "ok", "missing": []},
        thesis={"summary": "Quality compounder"},
        risk={"max_drawdown_decimal": -0.12},
        valuation_status="approved",
        portfolio_fit={"over_concentrated": False},
        lens_ensemble={"synthesis_labels": ["quality_supportive"]},
    )
    decision = evaluate_holding_decision(context)
    assert decision["action"] == "Review add"
    assert decision["order_generated"] is False


def test_decision_center_never_generates_orders() -> None:
    for scenario in supported_scenarios():
        decision = evaluate_holding_decision(scenario)
        assert decision["order_generated"] is False
        assert decision["requires_user_confirmation"] is True
        personal = to_personal_decision_support(action=decision["action"])
        assert personal.order_generated is False
        assert personal.requires_user_confirmation is True
        assert personal.outcome in set(DecisionOutcome)

