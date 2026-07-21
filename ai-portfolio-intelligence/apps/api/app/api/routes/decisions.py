"""Decision queue and packet lifecycle API (beyond decision_center overview)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth_deps import Principal, get_current_principal
from app.api.deps import get_broker_adapter
from app.db.decision_packet_repo import DecisionPacketRepository
from app.schemas.decision_packet import DecisionUserResponse
from app.services.broker.base import BrokerAdapter
from app.services.decision_center.outcome_tracker import (
    list_outcome_history,
    list_outcome_observations,
    record_outcome_transition,
)
from app.services.decision_center.user_response_service import list_responses, record_user_response

router = APIRouter(
    prefix="/decisions",
    tags=["decisions"],
    dependencies=[Depends(get_current_principal)],
)


@router.get("/queue")
def decision_queue(
    account_id: str | None = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    from app.api.routes.decision_center import decision_center_overview

    summary_account = None
    packets = []
    try:
        from app.api.routes.portfolio import _resolve_account_data

        summary, _positions = _resolve_account_data(adapter, account_id, principal)
        summary_account = summary.account_id
        packets = DecisionPacketRepository().list_for_account(summary.account_id)
    except Exception:
        summary_account = account_id or "default"

    queue = []
    for packet in packets:
        if packet.outcome.value == "monitor" and not packet.outcome_changed:
            continue
        queue.append(
            {
                "decision_id": packet.decision_id,
                "instrument_key": packet.instrument_key,
                "symbol": packet.symbol,
                "outcome": packet.outcome.value,
                "previous_outcome": packet.previous_outcome.value if packet.previous_outcome else None,
                "priority": packet.priority,
                "confidence_status": packet.confidence_status,
                "implementation_status": str(packet.implementation_status),
                "blockers": packet.blockers,
                "gates_failed": [g.gate_id for g in packet.gates if not g.passed],
                "order_generated": False,
            }
        )

    # Live fallback: evaluate Decision Center matrix when no stored attention items.
    if not queue:
        matrix = decision_center_overview(
            adapter=adapter,
            principal=principal,
            account_id=account_id,
        )
        summary_account = str(matrix.get("account_id") or summary_account)
        for row in matrix.get("holdings") or []:
            outcome = row.get("outcome") or "monitor"
            if outcome == "monitor":
                continue
            queue.append(
                {
                    "decision_id": row.get("decision_id"),
                    "instrument_key": row.get("instrument_key"),
                    "symbol": row.get("symbol"),
                    "outcome": outcome,
                    "previous_outcome": None,
                    "priority": row.get("priority") or "routine",
                    "confidence_status": row.get("confidence_status") or "provisional",
                    "implementation_status": row.get("implementation_status") or "blocked",
                    "blockers": row.get("blockers") or [],
                    "gates_failed": [
                        g.get("gate") or g.get("gate_id")
                        for g in (row.get("gates") or [])
                        if isinstance(g, dict) and not g.get("passed", True)
                    ],
                    "order_generated": False,
                }
            )

    priority_rank = {"urgent": 0, "critical": 0, "this_week": 1, "high": 1, "routine": 2, "low": 3}
    queue.sort(key=lambda row: (priority_rank.get(str(row.get("priority")), 9), row.get("symbol") or ""))
    return {
        "account_id": summary_account,
        "queue": queue,
        "count": len(queue),
        "order_generated": False,
    }


@router.get("/history/{instrument_key}")
def decision_history(
    instrument_key: str,
    account_id: str | None = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    from app.api.routes.portfolio import _resolve_account_data

    summary, _positions = _resolve_account_data(adapter, account_id, principal)
    return {
        "account_id": summary.account_id,
        "instrument_key": instrument_key,
        "history": list_outcome_history(summary.account_id, instrument_key),
        "observations": list_outcome_observations(summary.account_id, instrument_key),
        "order_generated": False,
    }


@router.get("/{decision_id}")
def get_decision(decision_id: str) -> dict[str, Any]:
    packet = DecisionPacketRepository().get(decision_id)
    if packet is None:
        raise HTTPException(status_code=404, detail="decision_not_found")
    payload = packet.model_dump(mode="json")
    payload["order_generated"] = False
    payload["user_responses"] = list_responses(decision_id)
    return payload


@router.post("/{decision_id}/respond")
def respond_to_decision(decision_id: str, body: DecisionUserResponse) -> dict[str, Any]:
    if body.decision_id != decision_id:
        raise HTTPException(status_code=400, detail="decision_id_mismatch")
    packet = DecisionPacketRepository().get(decision_id)
    if packet is None:
        raise HTTPException(status_code=404, detail="decision_not_found")
    recorded = record_user_response(body)
    try:
        from app.services.validation.decision_calibration import record_calibration_observation

        record_calibration_observation(
            decision_id=packet.decision_id,
            outcome=packet.outcome.value,
            user_response=body.response,
        )
    except Exception:
        pass
    if packet.previous_outcome and packet.previous_outcome != packet.outcome:
        record_outcome_transition(
            account_id=packet.account_id,
            instrument_key=packet.instrument_key,
            decision_id=packet.decision_id,
            previous_outcome=packet.previous_outcome.value if packet.previous_outcome else None,
            outcome=packet.outcome.value,
            change_reason_codes=packet.change_reason_codes,
        )
    return {"ok": True, "response": recorded, "order_generated": False}
