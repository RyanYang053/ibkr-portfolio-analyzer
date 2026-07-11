from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.api.account_deps import resolve_authorized_account_id
from app.api.auth_deps import Principal, get_current_principal
from app.api.deps import broker_not_configured_error, get_broker_adapter
from app.services.broker.base import BrokerAdapter
from app.services.portfolio.account_scope import find_portfolio_position
from app.services.portfolio.snapshot import gate_professional_response
from app.services.scoring.decision_engine import build_recommendation

router = APIRouter(
    prefix="/recommendations",
    tags=["recommendations"],
    dependencies=[Depends(get_current_principal)],
)


def _positions(
    adapter: BrokerAdapter,
    principal: Principal,
    account_id: Optional[str] = None,
):
    try:
        active_id = resolve_authorized_account_id(account_id, adapter, principal)
        return active_id, adapter.get_positions(active_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise broker_not_configured_error(exc) from exc


@router.get("")
def recommendations(
    account_id: Optional[str] = None,
    con_id: Optional[int] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    active_id, positions = _positions(adapter, principal, account_id)
    if con_id is not None:
        position = find_portfolio_position("", adapter, active_id, con_id)
        positions = [position] if position is not None else []
    recs = [build_recommendation(position).model_dump() for position in positions]
    return gate_professional_response(adapter, principal, active_id, {"recommendations": recs})


@router.get("/{symbol}")
def recommendation(
    symbol: str,
    account_id: Optional[str] = None,
    con_id: Optional[int] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    active_id = resolve_authorized_account_id(account_id, adapter, principal)
    try:
        position = find_portfolio_position(symbol, adapter, active_id, con_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise broker_not_configured_error(exc) from exc
    if position is None:
        return {"status": "not_found"}
    return gate_professional_response(adapter, principal, active_id, build_recommendation(position).model_dump())


@router.post("/generate")
def generate(
    account_id: Optional[str] = None,
    con_id: Optional[int] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    active_id, positions = _positions(adapter, principal, account_id)
    if con_id is not None:
        position = find_portfolio_position("", adapter, active_id, con_id)
        positions = [position] if position is not None else []
    recs = [build_recommendation(position).model_dump() for position in positions]
    return gate_professional_response(adapter, principal, active_id, {"recommendations": recs})
