"""Monitoring API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.api.auth_deps import Principal, get_current_principal
from app.api.deps import get_broker_adapter
from app.services.broker.base import BrokerAdapter
from app.services.decision_center.monitoring_service import (
    acknowledge_monitoring_event,
    list_monitoring_events,
    resolve_monitoring_event,
    run_monitoring_evaluation,
    snooze_monitoring_event,
)
from app.services.notifications import outbox
from app.services.notifications.dispatcher import flush_pending

router = APIRouter(
    prefix="/monitoring",
    tags=["monitoring"],
    dependencies=[Depends(get_current_principal)],
)


@router.get("/events")
def monitoring_events(
    account_id: str | None = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    from app.api.routes.portfolio import _resolve_account_data

    summary, _positions = _resolve_account_data(adapter, account_id, principal)
    resolved = summary.account_id
    return {
        "account_id": resolved,
        "events": list_monitoring_events(resolved),
        "order_generated": False,
    }


@router.post("/evaluate")
def evaluate_monitoring(
    account_id: str | None = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    from app.api.routes.portfolio import _resolve_account_data

    summary, positions = _resolve_account_data(adapter, account_id, principal)
    holdings = [
        {
            "symbol": p.symbol,
            "instrument_key": f"{p.symbol}:{p.con_id}" if p.con_id else p.symbol,
            "portfolio_weight": float(getattr(p, "portfolio_weight", 0) or 0),
        }
        for p in positions
        if getattr(p, "asset_class", None) not in {"OPT", "FOP", "CASH"}
    ]
    return run_monitoring_evaluation(account_id=summary.account_id, holdings=holdings)


@router.post("/events/{event_id}/acknowledge")
def acknowledge_event(event_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    updated = acknowledge_monitoring_event(event_id, note=(body or {}).get("note"))
    if updated is None:
        return {"ok": False, "error": "event_not_found", "order_generated": False}
    return {"ok": True, "event": updated, "order_generated": False}


@router.post("/events/{event_id}/resolve")
def resolve_event(event_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    updated = resolve_monitoring_event(event_id, note=(body or {}).get("note"))
    if updated is None:
        return {"ok": False, "error": "event_not_found", "order_generated": False}
    return {"ok": True, "event": updated, "order_generated": False}


@router.post("/events/{event_id}/snooze")
def snooze_event(event_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = body or {}
    snooze_until = payload.get("snooze_until")
    if not snooze_until:
        return {"ok": False, "error": "snooze_until_required", "order_generated": False}
    updated = snooze_monitoring_event(
        event_id,
        snooze_until=str(snooze_until),
        note=payload.get("note"),
    )
    if updated is None:
        return {"ok": False, "error": "event_not_found", "order_generated": False}
    return {"ok": True, "event": updated, "order_generated": False}


@router.get("/notifications")
def notifications(
    account_id: str | None = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    from app.api.routes.portfolio import _resolve_account_data
    from app.services.notifications.desktop import read_desktop_inbox

    summary, _positions = _resolve_account_data(adapter, account_id, principal)
    return {
        "account_id": summary.account_id,
        "notifications": outbox.list_for_account(summary.account_id),
        "desktop_inbox": read_desktop_inbox(),
        "order_generated": False,
    }


@router.post("/notifications/flush")
def flush_notifications() -> dict[str, Any]:
    delivered = flush_pending()
    return {"delivered": delivered, "count": len(delivered), "order_generated": False}


@router.get("/options-expiry")
def options_expiry(
    account_id: str | None = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    from app.api.routes.portfolio import _resolve_account_data
    from app.services.options.expiry_calendar import build_options_expiry_calendar

    summary, positions = _resolve_account_data(adapter, account_id, principal)
    payload = [
        {
            "symbol": p.symbol,
            "instrument_key": f"{p.symbol}:{p.con_id}" if p.con_id else p.symbol,
            "asset_class": getattr(p, "asset_class", None),
            "expiry": getattr(p, "expiry", None) or getattr(p, "lastTradeDateOrContractMonth", None),
        }
        for p in positions
    ]
    calendar = build_options_expiry_calendar(payload)
    calendar["account_id"] = summary.account_id
    return calendar
