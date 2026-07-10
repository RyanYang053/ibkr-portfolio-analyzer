from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth_deps import get_current_principal
from app.api.deps import broker_not_configured_error, get_broker_adapter
from app.services.broker.base import BrokerAdapter
from app.services.portfolio.account_scope import resolve_portfolio_account_id
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
):
    try:
        active_id = resolve_portfolio_account_id(account_id, adapter)
        return analyze_portfolio_risk(
            adapter.get_account_summary(active_id),
            adapter.get_positions(active_id),
        ).alerts
    except HTTPException:
        raise
    except Exception as exc:
        raise broker_not_configured_error(exc) from exc


@router.put("/{alert_id}/resolve")
def resolve_alert(alert_id: int):
    return {"id": alert_id, "is_resolved": True}
