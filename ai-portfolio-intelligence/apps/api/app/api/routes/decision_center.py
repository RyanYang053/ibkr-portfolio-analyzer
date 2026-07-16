from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.account_deps import resolve_authorized_account_id
from app.api.auth_deps import Principal, get_current_principal
from app.api.deps import get_broker_adapter
from app.services.broker.base import BrokerAdapter
from app.services.data_quality.validation import prepare_professional_response, validate_and_gate_snapshot
from app.services.decision_center.action_simulator import simulate_holding_action
from app.services.decision_center.evidence_graph import build_evidence_graph
from app.services.decision_center.holding_context import build_holding_context
from app.services.decision_center.holding_decision import evaluate_holding_decision
from app.services.decision_center.market_inputs import load_account_risk_bundle, load_holding_market_inputs
from app.services.decision_center.monitoring_rules import (
    create_monitoring_rule,
    evaluate_monitoring_rules,
    list_monitoring_rules,
)
from app.services.decision_center.portfolio_decision import build_portfolio_decision_matrix
from app.services.decision_center.thesis_service import get_thesis, put_thesis
from app.services.investor_lenses import ensemble_synthesis, evaluate_all_lenses
from app.services.investor_lenses.base import LensInputs

router = APIRouter(
    prefix="/portfolio",
    tags=["decision-center"],
    dependencies=[Depends(get_current_principal)],
)


class ThesisPutRequest(BaseModel):
    text: str = Field(min_length=1)
    author: str | None = None


class SimulateRequest(BaseModel):
    action: str
    proposed_weight: float | None = None
    estimated_tax: float | None = None


class MonitoringRuleRequest(BaseModel):
    instrument_key: str | None = None
    rule_type: str
    threshold: float | None = None
    note: str | None = None


def _snapshot(adapter: BrokerAdapter, account_id: str):
    summary = adapter.get_account_summary(account_id)
    positions = adapter.get_positions(account_id)
    validation = validate_and_gate_snapshot(summary, positions)
    return summary, positions, validation


def _position_payload(position) -> dict[str, Any]:
    return {
        "symbol": position.symbol,
        "instrument_key": f"{position.symbol}:{position.con_id}" if position.con_id else position.symbol,
        "portfolio_weight": float(getattr(position, "portfolio_weight", 0) or 0),
        "weight": float(getattr(position, "portfolio_weight", 0) or 0),
        "asset_class": position.asset_class,
        "stock_type": getattr(position, "stock_type", None),
        "market_value": float(position.market_value),
        "quantity": float(position.quantity),
        "con_id": position.con_id,
    }


@router.get("/decision-center")
def decision_center_overview(
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
    account_id: str | None = None,
) -> dict[str, Any]:
    resolved = resolve_authorized_account_id(adapter, principal, account_id)
    summary, positions, validation = _snapshot(adapter, resolved)
    cached_risk = load_account_risk_bundle(account_id=resolved, positions=positions, summary=summary)
    holdings = []
    for position in positions:
        if position.asset_class in {"OPT", "FOP", "CASH"}:
            continue
        payload = _position_payload(position)
        thesis = get_thesis(resolved, payload["instrument_key"]) or {}
        market = load_holding_market_inputs(
            symbol=position.symbol,
            account_id=resolved,
            positions=positions,
            summary=summary,
            cached_risk=cached_risk,
        )
        holdings.append(
            {
                **payload,
                "position": payload,
                "thesis": thesis,
                "fundamentals": market["fundamentals"],
                "risk_metrics": market["risk_metrics"],
                "factor_exposures": market["factor_exposures"],
            }
        )
    matrix = build_portfolio_decision_matrix(account_id=resolved, holdings=holdings)
    return prepare_professional_response(
        matrix,
        summary,
        positions,
        validation,
        methodology_id="decision_center_holding",
    )


@router.get("/holdings/{instrument_key}/decision")
def holding_decision(
    instrument_key: str,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
    account_id: str | None = None,
) -> dict[str, Any]:
    resolved = resolve_authorized_account_id(adapter, principal, account_id)
    summary, positions, validation = _snapshot(adapter, resolved)
    position = _find_position(positions, instrument_key)
    if position is None:
        raise HTTPException(status_code=404, detail="holding_not_found")
    payload = _position_payload(position)
    thesis = get_thesis(resolved, payload["instrument_key"]) or {}
    market = load_holding_market_inputs(
        symbol=position.symbol,
        account_id=resolved,
        positions=positions,
        summary=summary,
    )
    context = build_holding_context(
        account_id=resolved,
        instrument_key=payload["instrument_key"],
        symbol=position.symbol,
        position=payload,
        fundamentals=market["fundamentals"],
        risk_metrics=market["risk_metrics"],
        factor_exposures=market["factor_exposures"],
        thesis=thesis,
    )
    decision = evaluate_holding_decision(context)
    result = {
        **decision,
        "context": context.as_dict(),
        "evidence_graph": build_evidence_graph(context.as_dict()),
    }
    return prepare_professional_response(
        result,
        summary,
        positions,
        validation,
        methodology_id="decision_center_holding",
    )


@router.get("/holdings/{instrument_key}/lenses")
def holding_lenses(
    instrument_key: str,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
    account_id: str | None = None,
) -> dict[str, Any]:
    resolved = resolve_authorized_account_id(adapter, principal, account_id)
    summary, positions, validation = _snapshot(adapter, resolved)
    position = _find_position(positions, instrument_key)
    if position is None:
        raise HTTPException(status_code=404, detail="holding_not_found")
    payload = _position_payload(position)
    market = load_holding_market_inputs(
        symbol=position.symbol,
        account_id=resolved,
        positions=positions,
        summary=summary,
    )
    results = evaluate_all_lenses(
        LensInputs(
            symbol=position.symbol,
            position=payload,
            fundamentals=market["fundamentals"],
            risk_metrics=market["risk_metrics"],
            factor_exposures=market["factor_exposures"],
        )
    )
    body = {
        "instrument_key": payload["instrument_key"],
        "symbol": position.symbol,
        "lenses": [item.as_dict() for item in results],
        "ensemble": ensemble_synthesis(results),
        "methodology_status": "experimental",
        "note": "Lens scores are deterministic; LLM must not compute scores.",
        "inputs_present": {
            "fundamentals": bool(market["fundamentals"]),
            "risk_metrics": bool(market["risk_metrics"]),
            "factor_exposures": bool(market["factor_exposures"]),
        },
    }
    return prepare_professional_response(
        body,
        summary,
        positions,
        validation,
        methodology_id="decision_center_holding",
    )


@router.get("/holdings/{instrument_key}/thesis")
def get_holding_thesis(
    instrument_key: str,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
    account_id: str | None = None,
) -> dict[str, Any]:
    resolved = resolve_authorized_account_id(adapter, principal, account_id)
    summary, positions, validation = _snapshot(adapter, resolved)
    thesis = get_thesis(resolved, instrument_key) or {
        "account_id": resolved,
        "instrument_key": instrument_key,
        "text": "",
        "version": 0,
    }
    return prepare_professional_response(
        thesis,
        summary,
        positions,
        validation,
        methodology_id="decision_center_holding",
    )


@router.put("/holdings/{instrument_key}/thesis")
def put_holding_thesis(
    instrument_key: str,
    body: ThesisPutRequest,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
    account_id: str | None = None,
) -> dict[str, Any]:
    resolved = resolve_authorized_account_id(adapter, principal, account_id)
    summary, positions, validation = _snapshot(adapter, resolved)
    saved = put_thesis(resolved, instrument_key, text=body.text, author=body.author)
    return prepare_professional_response(
        saved,
        summary,
        positions,
        validation,
        methodology_id="decision_center_holding",
    )


@router.post("/holdings/{instrument_key}/simulate")
def simulate_holding(
    instrument_key: str,
    body: SimulateRequest,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
    account_id: str | None = None,
) -> dict[str, Any]:
    resolved = resolve_authorized_account_id(adapter, principal, account_id)
    summary, positions, validation = _snapshot(adapter, resolved)
    position = _find_position(positions, instrument_key)
    weight = float(getattr(position, "portfolio_weight", 0) or 0) if position else 0.0
    market = load_holding_market_inputs(
        symbol=(getattr(position, "symbol", None) or instrument_key.split(":")[0]),
        account_id=resolved,
        positions=positions,
        summary=summary,
    )
    profile_type = None
    jurisdiction = None
    try:
        from app.services.suitability.engine import get_investor_profile

        profile = get_investor_profile(resolved, user_id=principal.user_id)
        profile_type = getattr(profile, "account_type", None)
        residency = getattr(profile, "tax_residency", None)
        if residency == "Canada":
            jurisdiction = "CA"
        elif residency == "US":
            jurisdiction = "US"
    except Exception:
        profile_type = None
        jurisdiction = None
    sim = simulate_holding_action(
        action=body.action,
        current_weight=weight,
        proposed_weight=body.proposed_weight,
        estimated_tax=body.estimated_tax,
        account_id=resolved,
        symbol=getattr(position, "symbol", None) if position else instrument_key.split(":")[0],
        position=position,
        summary=summary,
        risk_metrics=market.get("risk_metrics") or {},
        tax_jurisdiction=jurisdiction,
        account_type=str(profile_type) if profile_type else None,
    )
    sim["instrument_key"] = instrument_key
    return prepare_professional_response(
        sim,
        summary,
        positions,
        validation,
        methodology_id="decision_center_holding",
    )


@router.get("/decision-monitoring")
def get_decision_monitoring(
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
    account_id: str | None = None,
) -> dict[str, Any]:
    resolved = resolve_authorized_account_id(adapter, principal, account_id)
    summary, positions, validation = _snapshot(adapter, resolved)
    holdings = []
    theses: dict[str, dict[str, Any]] = {}
    for position in positions:
        key = f"{position.symbol}:{position.con_id}" if getattr(position, "con_id", None) else position.symbol
        holdings.append(
            {
                "instrument_key": key,
                "symbol": position.symbol,
                "portfolio_weight": float(getattr(position, "portfolio_weight", 0) or 0),
            }
        )
        thesis = get_thesis(resolved, key)
        if thesis:
            theses[key.upper()] = thesis
    risk_metrics, _factors = load_account_risk_bundle(account_id=resolved, positions=positions, summary=summary)
    evaluation = evaluate_monitoring_rules(
        resolved,
        holdings=holdings,
        risk_metrics=risk_metrics,
        theses=theses,
    )
    body = {
        "account_id": resolved,
        "rules": list_monitoring_rules(resolved),
        "evaluation": evaluation,
        "methodology_status": "experimental",
    }
    return prepare_professional_response(
        body,
        summary,
        positions,
        validation,
        methodology_id="decision_center_holding",
    )


@router.post("/decision-monitoring")
def post_decision_monitoring(
    body: MonitoringRuleRequest,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
    account_id: str | None = None,
) -> dict[str, Any]:
    resolved = resolve_authorized_account_id(adapter, principal, account_id)
    summary, positions, validation = _snapshot(adapter, resolved)
    rule = create_monitoring_rule(
        resolved,
        instrument_key=body.instrument_key,
        rule_type=body.rule_type,
        threshold=body.threshold,
        note=body.note,
    )
    return prepare_professional_response(
        rule,
        summary,
        positions,
        validation,
        methodology_id="decision_center_holding",
    )


def _find_position(positions, instrument_key: str):
    key = instrument_key.upper()
    for position in positions:
        payload = _position_payload(position)
        if payload["instrument_key"].upper() == key or position.symbol.upper() == key:
            return position
        if position.con_id is not None and key.endswith(f":{position.con_id}"):
            return position
    return None
