from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth_deps import get_current_principal
from app.api.deps import broker_not_configured_error, get_broker_adapter
from app.services.broker.base import BrokerAdapter
from app.services.portfolio.account_scope import resolve_portfolio_account_id
from app.services.scoring.decision_engine import build_recommendation


router = APIRouter(
    prefix="/recommendations",
    tags=["recommendations"],
    dependencies=[Depends(get_current_principal)],
)


def _positions(adapter: BrokerAdapter, account_id: Optional[str] = None):
    try:
        active_id = resolve_portfolio_account_id(account_id, adapter)
        return adapter.get_positions(active_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise broker_not_configured_error(exc) from exc


@router.get("")
def recommendations(
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
):
    positions = _positions(adapter, account_id)
    return [build_recommendation(position) for position in positions]


@router.get("/{symbol}")
def recommendation(
    symbol: str,
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
):
    for position in _positions(adapter, account_id):
        if position.symbol == symbol.upper():
            return build_recommendation(position)
    return {"status": "not_found"}


@router.post("/generate")
def generate(
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
):
    positions = _positions(adapter, account_id)
    return {"recommendations": [build_recommendation(position) for position in positions]}
