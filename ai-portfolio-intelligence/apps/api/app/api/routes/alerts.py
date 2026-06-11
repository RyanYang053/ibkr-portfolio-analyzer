from fastapi import APIRouter, Depends

from app.api.deps import broker_not_configured_error, get_broker_adapter
from app.services.broker.base import BrokerAdapter
from app.services.risk.portfolio_risk import analyze_portfolio_risk


router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("")
def alerts(adapter: BrokerAdapter = Depends(get_broker_adapter)):
    try:
        account_id = adapter.get_accounts()[0].id
        return analyze_portfolio_risk(adapter.get_account_summary(account_id), adapter.get_positions(account_id)).alerts
    except Exception as exc:
        raise broker_not_configured_error(exc) from exc


@router.put("/{alert_id}/resolve")
def resolve_alert(alert_id: int):
    return {"id": alert_id, "is_resolved": True}
