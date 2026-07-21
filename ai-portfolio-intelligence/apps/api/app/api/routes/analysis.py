"""Recommendations API — score interpretations only (deprecated as authority)."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.api.account_deps import resolve_portfolio_scope_id
from app.api.auth_deps import Principal, get_current_principal
from app.api.deps import broker_not_configured_error, get_broker_adapter
from app.services.broker.base import BrokerAdapter
from app.services.portfolio.account_scope import find_portfolio_position
from app.services.portfolio.snapshot import gate_professional_response
from app.services.scoring.decision_engine import score_interpretation_payload

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
        from app.api.routes.portfolio import _resolve_account_data

        summary, positions = _resolve_account_data(adapter, account_id, principal)
        return summary.account_id, positions
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
    recs = [score_interpretation_payload(position) for position in positions]
    return gate_professional_response(
        adapter,
        principal,
        active_id,
        {
            "recommendations": recs,
            "deprecated": True,
            "authoritative": False,
            "note": "Use /portfolio/decision-center or /portfolio/decisions for authoritative outcomes.",
        },
    )


@router.get("/{symbol}")
def recommendation(
    symbol: str,
    account_id: Optional[str] = None,
    con_id: Optional[int] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    active_id = resolve_portfolio_scope_id(account_id, adapter, principal)
    try:
        position = find_portfolio_position(symbol, adapter, active_id, con_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise broker_not_configured_error(exc) from exc
    if position is None:
        return {"status": "not_found"}
    payload = score_interpretation_payload(position)
    payload["deprecated"] = True
    payload["authoritative"] = False
    payload["note"] = "Use /portfolio/decision-center or /portfolio/decisions for authoritative outcomes."
    return gate_professional_response(adapter, principal, active_id, payload)


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
    recs = [score_interpretation_payload(position) for position in positions]
    return gate_professional_response(
        adapter,
        principal,
        active_id,
        {"recommendations": recs, "deprecated": True, "authoritative": False},
    )
