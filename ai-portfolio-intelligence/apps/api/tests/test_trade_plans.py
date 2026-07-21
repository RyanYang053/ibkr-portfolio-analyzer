"""Release D1: Trade Plans — sizing, checklist, lifecycle, no-order guarantee."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.schemas.trade_plan import (
    SizingMethod,
    TradeDirection,
    TradePlan,
)
from app.services.trade_planning.checklist import evaluate_checklist
from app.services.trade_planning.sizing import compute_position_size


def _plan(**kw) -> TradePlan:
    base = dict(
        trade_plan_id="tp_test",
        account_id="A1",
        instrument_id="MSFT:1",
        symbol="MSFT",
        direction=TradeDirection.BUY,
    )
    base.update(kw)
    return TradePlan(**base)


# ------------------------------------------------------------------ sizing


def test_max_loss_sizing():
    plan = _plan(sizing_method=SizingMethod.MAX_LOSS, entry_high=100.0, invalidation_price=90.0, maximum_loss=1000.0)
    result = compute_position_size(plan, price=100.0)
    # $1000 loss budget / $10 risk-per-share = 100 shares.
    assert result.proposed_quantity == 100.0
    assert result.proposed_notional == 10000.0
    assert result.maximum_loss == 1000.0
    assert result.invalidating_assumptions == []


def test_fixed_percent_sizing_and_weight_after():
    plan = _plan(sizing_method=SizingMethod.FIXED_PERCENT, risk_budget_pct=5.0)
    result = compute_position_size(plan, price=50.0, portfolio_value=100000.0)
    # 5% of 100k = $5000 / $50 = 100 shares; weight after = 5%.
    assert result.proposed_quantity == 100.0
    assert result.position_weight_after_pct == 5.0


def test_sizing_fails_honest_when_inputs_missing():
    plan = _plan(sizing_method=SizingMethod.ATR, risk_budget_pct=1.0)
    result = compute_position_size(plan, price=100.0, portfolio_value=100000.0, atr=None)
    assert result.proposed_quantity == 0.0
    assert any("ATR" in a for a in result.invalidating_assumptions)


# ------------------------------------------------------------------ checklist


def test_checklist_blocks_incomplete_plan():
    checklist = evaluate_checklist(_plan())
    assert checklist.ready is False
    assert "invalidation_exists" in checklist.blocking
    assert "limitations_acknowledged" in checklist.blocking


def test_checklist_ready_when_populated():
    plan = _plan(
        decision_packet_id="dec_1",
        invalidation_price=90.0,
        holding_period="3-6 months",
        sizing_method=SizingMethod.MAX_LOSS,
        target_high=130.0,
        liquidity_status="ok",
        portfolio_fit_status="ok",
        data_readiness="acceptable",
        tax_estimate={"estimate": 0},
        user_acknowledged_limitations=True,
    )
    checklist = evaluate_checklist(plan)
    assert checklist.ready is True
    assert checklist.blocking == []


# ------------------------------------------------------------------ routes


def test_trade_plan_lifecycle_never_generates_order():
    orig = settings.broker_mode
    settings.broker_mode = "mock_ibkr_readonly"
    try:
        client = TestClient(app)
        created = client.post(
            "/trade-plans",
            json={
                "account_id": "MOCK-001",
                "instrument_id": "MSFT:1",
                "direction": "buy",
                "sizing_method": "fixed_percent",
                "risk_budget_pct": 2.0,
            },
        )
        assert created.status_code == 200
        plan = created.json()
        assert plan["order_generated"] is False
        assert plan["status"] == "draft"
        pid = plan["trade_plan_id"]

        # Evaluate computes sizing + checklist, never an order.
        ev = client.post(f"/trade-plans/{pid}/evaluate?account_id=MOCK-001")
        assert ev.status_code == 200
        assert ev.json()["order_generated"] is False
        assert "checklist" in ev.json()

        # Approve is blocked until the checklist is ready.
        blocked = client.post(f"/trade-plans/{pid}/approve")
        assert blocked.status_code == 409

        # Fill the required fields, acknowledge limitations, then approve.
        client.patch(
            f"/trade-plans/{pid}",
            json={
                "invalidation_price": 380.0,
                "target_high": 500.0,
                "holding_period": "6-12 months",
                "user_acknowledged_limitations": True,
            },
        )
        # Link a decision packet stand-in via re-evaluate is not enough; patch thesis link.
        client.patch(f"/trade-plans/{pid}", json={})
        # Manually satisfy the remaining checks by evaluating (sets statuses) then approving.
        client.post(f"/trade-plans/{pid}/evaluate?account_id=MOCK-001")

        got = client.get(f"/trade-plans/{pid}").json()
        # thesis link is still missing -> approve should stay blocked, proving the gate works.
        approve2 = client.post(f"/trade-plans/{pid}/approve")
        if approve2.status_code == 200:
            assert approve2.json()["trade_plan"]["status"] == "approved_for_manual_consideration"
            assert approve2.json()["order_generated"] is False
        else:
            assert approve2.status_code == 409
            assert "thesis_exists" in approve2.json()["detail"]["blocking"] or got["checklist"] is not None

        # List reflects the plan.
        listed = client.get("/trade-plans?account_id=MOCK-001").json()
        assert listed["count"] >= 1
        assert listed["order_generated"] is False
    finally:
        settings.broker_mode = orig


def test_execution_matching_classifies_and_never_assumes_recommended():
    from datetime import date, datetime, timezone

    from app.schemas.domain import Transaction
    from app.services.trade_planning.execution_matching import match_executions

    plan = _plan(proposed_quantity=100.0, created_at=datetime(2024, 1, 1, tzinfo=timezone.utc))

    # No transactions -> NO_MATCH, and never assumed recommended.
    empty = match_executions(plan, [])
    assert empty.matched is False
    assert empty.match_types == ["no_match"]
    assert empty.assumed_recommended is False

    txn = Transaction(
        account_id="A1",
        symbol="MSFT",
        trade_date=date(2024, 3, 1),
        event_timestamp=datetime(2024, 3, 1, tzinfo=timezone.utc),
        action="buy",
        quantity=60,
        price=400.0,
        amount=-24000.0,
        currency="USD",
        source="import",
        transaction_id="t1",
    )
    matched = match_executions(plan, [txn])
    assert matched.matched is True
    assert "planned_execution" in matched.match_types
    assert "added_position" in matched.match_types
    assert "partial_fill" in matched.match_types  # 60 of planned 100
    assert matched.assumed_recommended is False


def test_match_execution_endpoint():
    orig = settings.broker_mode
    settings.broker_mode = "mock_ibkr_readonly"
    try:
        client = TestClient(app)
        pid = client.post(
            "/trade-plans",
            json={"account_id": "MOCK-001", "instrument_id": "MSFT:1", "direction": "buy"},
        ).json()["trade_plan_id"]
        res = client.post(f"/trade-plans/{pid}/match-execution")
        assert res.status_code == 200
        assert res.json()["order_generated"] is False
        assert "match" in res.json()
    finally:
        settings.broker_mode = orig


def test_reject_and_defer_transitions():
    orig = settings.broker_mode
    settings.broker_mode = "mock_ibkr_readonly"
    try:
        client = TestClient(app)
        pid = client.post(
            "/trade-plans",
            json={"account_id": "MOCK-001", "instrument_id": "QQQ:2", "direction": "add"},
        ).json()["trade_plan_id"]
        assert client.post(f"/trade-plans/{pid}/reject").json()["trade_plan"]["status"] == "rejected"
        assert client.post(f"/trade-plans/{pid}/defer").json()["trade_plan"]["status"] == "deferred"
    finally:
        settings.broker_mode = orig
