from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.api.account_deps import resolve_authorized_account_id
from app.api.auth_deps import Principal, get_current_principal
from app.api.deps import broker_not_configured_error, get_broker_adapter
from app.db.resolved_alert_repo import is_resolved, resolve_alert as persist_resolve_alert
from app.services.broker.base import BrokerAdapter
from app.services.data_quality.validation import validate_and_gate_snapshot
from app.services.risk.portfolio_risk import analyze_portfolio_risk

router = APIRouter(
    prefix="/alerts",
    tags=["alerts"],
    dependencies=[Depends(get_current_principal)],
)


@router.get("")
def alerts(
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    try:
        active_id = resolve_authorized_account_id(account_id, adapter, principal)
        summary = adapter.get_account_summary(active_id)
        positions = adapter.get_positions(active_id)
        validate_and_gate_snapshot(summary, positions)
        raw = analyze_portfolio_risk(summary, positions).alerts
        result = []
        for idx, alert in enumerate(raw):
            payload = alert.model_dump() if hasattr(alert, "model_dump") else dict(alert)
            alert_id = int(payload.get("id") or idx)
            payload["id"] = alert_id
            payload["is_resolved"] = is_resolved(alert_id)
            if not payload["is_resolved"]:
                result.append(payload)
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise broker_not_configured_error(exc) from exc


@router.put("/{alert_id}/resolve")
def resolve_alert(alert_id: int, account_id: Optional[str] = None):
    return persist_resolve_alert(alert_id, account_id=account_id)
