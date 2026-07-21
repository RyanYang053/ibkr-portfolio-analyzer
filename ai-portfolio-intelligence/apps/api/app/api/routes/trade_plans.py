"""Trade Plans API (plan §9 / §19).

Trade Plans are auditable intentions, never orders. There is deliberately no
"submit"/"place"/"execute" surface here: the strongest state is
"approved for manual consideration", which the user acts on inside their broker.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth_deps import Principal, get_current_principal
from app.api.deps import get_broker_adapter
from app.db.instruments_repository import resolve_instrument
from app.db.trade_plan_repo import get_trade_plan, list_trade_plans, save_trade_plan
from app.schemas.trade_plan import (
    TradePlan,
    TradePlanCreate,
    TradePlanStatus,
    TradePlanUpdate,
)
from app.services.broker.base import BrokerAdapter
from app.services.trade_planning.checklist import evaluate_checklist
from app.services.trade_planning.sizing import compute_position_size

router = APIRouter(
    prefix="/trade-plans",
    tags=["trade-plans"],
    dependencies=[Depends(get_current_principal)],
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require(plan_id: str) -> TradePlan:
    plan = get_trade_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Unknown trade plan: {plan_id}")
    return plan


@router.get("")
def list_plans(
    account_id: str,
    status: str | None = None,
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    plans = list_trade_plans(account_id, status=status)
    return {
        "account_id": account_id,
        "count": len(plans),
        "trade_plans": [p.model_dump(mode="json") for p in plans],
        "order_generated": False,
    }


@router.post("")
def create_plan(
    body: TradePlanCreate,
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    symbol = (body.symbol or body.instrument_id.split(":", 1)[0]).strip().upper()
    # Register the instrument so the plan links to a canonical reference.
    resolve_instrument(symbol=symbol, con_id=None)
    plan = TradePlan(
        trade_plan_id=f"tp_{uuid4().hex[:16]}",
        account_id=body.account_id,
        instrument_id=body.instrument_id,
        symbol=symbol,
        direction=body.direction,
        plan_type=body.plan_type,
        status=TradePlanStatus.DRAFT,
        thesis_version_id=body.thesis_version_id,
        decision_packet_id=body.decision_packet_id,
        entry_low=body.entry_low,
        entry_high=body.entry_high,
        invalidation_price=body.invalidation_price,
        target_low=body.target_low,
        target_high=body.target_high,
        risk_budget_pct=body.risk_budget_pct,
        sizing_method=body.sizing_method,
        proposed_quantity=body.proposed_quantity,
        holding_period=body.holding_period,
        catalysts=body.catalysts,
        risks=body.risks,
        created_at=_now(),
    )
    save_trade_plan(plan)
    return plan.model_dump(mode="json")


@router.get("/{plan_id}")
def get_plan(plan_id: str, principal: Principal = Depends(get_current_principal)) -> dict[str, object]:
    return _require(plan_id).model_dump(mode="json")


@router.patch("/{plan_id}")
def update_plan(
    plan_id: str,
    body: TradePlanUpdate,
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    plan = _require(plan_id)
    if plan.status in {TradePlanStatus.CLOSED, TradePlanStatus.EXPIRED}:
        raise HTTPException(status_code=409, detail=f"Plan is {plan.status.value} and cannot be edited")
    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(plan, field, value)
    plan.reviewed_at = _now()
    save_trade_plan(plan)
    return plan.model_dump(mode="json")


def _portfolio_value(adapter: BrokerAdapter, account_id: str, principal: Principal) -> float | None:
    try:
        summary = adapter.get_account_summary(account_id)
        return float(getattr(summary, "net_liquidation", 0) or 0) or None
    except Exception:  # noqa: BLE001
        return None


def _held_price(adapter: BrokerAdapter, plan: TradePlan) -> tuple[float | None, str]:
    try:
        from app.services.portfolio.account_scope import find_portfolio_position

        symbol, _, con = plan.instrument_id.partition(":")
        con_id = int(con) if con.isdigit() else None
        held = find_portfolio_position(symbol, adapter, plan.account_id, con_id)
        if held is not None:
            return float(held.market_price), "acceptable"
    except Exception:  # noqa: BLE001
        pass
    return None, "unknown"


@router.post("/{plan_id}/evaluate")
def evaluate_plan(
    plan_id: str,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    """Compute sizing + the pre-trade checklist. Never generates an order."""
    plan = _require(plan_id)
    price, liquidity_status = _held_price(adapter, plan)
    portfolio_value = _portfolio_value(adapter, plan.account_id, principal)

    sizing = compute_position_size(plan, price=price, portfolio_value=portfolio_value)
    plan.sizing_method = sizing.method
    plan.proposed_quantity = sizing.proposed_quantity
    plan.proposed_notional = sizing.proposed_notional
    plan.maximum_loss = sizing.maximum_loss
    plan.resulting_position = plan.current_position + (
        sizing.proposed_quantity if plan.direction.value in {"buy", "add"} else -sizing.proposed_quantity
    )
    plan.liquidity_status = liquidity_status
    plan.data_readiness = "acceptable" if price is not None else "partial"
    plan.portfolio_fit_status = "ok" if sizing.position_weight_after_pct is not None else "unknown"
    plan.checklist = evaluate_checklist(plan)
    if plan.status == TradePlanStatus.DRAFT:
        plan.status = TradePlanStatus.UNDER_REVIEW
    plan.reviewed_at = _now()
    save_trade_plan(plan)
    return {
        "trade_plan": plan.model_dump(mode="json"),
        "sizing": sizing.model_dump(mode="json"),
        "checklist": plan.checklist.model_dump(mode="json"),
        "order_generated": False,
    }


def _transition(plan_id: str, new_status: TradePlanStatus, *, require_ready: bool = False) -> dict[str, object]:
    plan = _require(plan_id)
    if require_ready:
        checklist = plan.checklist or evaluate_checklist(plan)
        if not checklist.ready:
            raise HTTPException(
                status_code=409,
                detail={"error": "pre_trade_checklist_incomplete", "blocking": checklist.blocking},
            )
    plan.status = new_status
    plan.reviewed_at = _now()
    save_trade_plan(plan)
    return {"trade_plan": plan.model_dump(mode="json"), "order_generated": False}


@router.post("/{plan_id}/approve")
def approve_plan(plan_id: str, principal: Principal = Depends(get_current_principal)) -> dict[str, object]:
    """Approve for MANUAL consideration only. This never transmits anything to a broker."""
    return _transition(plan_id, TradePlanStatus.APPROVED_FOR_MANUAL_CONSIDERATION, require_ready=True)


@router.post("/{plan_id}/reject")
def reject_plan(plan_id: str, principal: Principal = Depends(get_current_principal)) -> dict[str, object]:
    return _transition(plan_id, TradePlanStatus.REJECTED)


@router.post("/{plan_id}/defer")
def defer_plan(plan_id: str, principal: Principal = Depends(get_current_principal)) -> dict[str, object]:
    return _transition(plan_id, TradePlanStatus.DEFERRED)
