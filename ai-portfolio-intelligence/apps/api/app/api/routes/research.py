"""Research queue API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth_deps import Principal, get_current_principal
from app.api.deps import get_broker_adapter
from app.db.decision_packet_repo import DecisionPacketRepository
from app.db.research_candidate_repo import ResearchCandidateRepository
from app.schemas.research_note import ResearchNoteCreate
from app.services.broker.base import BrokerAdapter
from app.services.research.candidate_comparison import compare_candidates
from app.services.research.catalyst_calendar import build_catalyst_calendar
from app.services.research.change_detector import detect_changes
from app.services.research.research_queue import ResearchQueueService

router = APIRouter(
    prefix="/research",
    tags=["research"],
    dependencies=[Depends(get_current_principal)],
)


class CompareRequest(BaseModel):
    left_candidate_id: str
    right_candidate_id: str


@router.get("/queue")
def research_queue(
    account_id: str | None = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    from app.api.routes.portfolio import _resolve_account_data

    summary, positions = _resolve_account_data(adapter, account_id, principal)
    resolved = summary.account_id
    holdings = []
    option_positions: list[dict[str, Any]] = []
    for position in positions:
        asset = getattr(position, "asset_class", None)
        if asset in {"OPT", "FOP"}:
            option_positions.append(
                {
                    "symbol": position.symbol,
                    "expiry": getattr(position, "expiry", None)
                    or getattr(position, "lastTradeDateOrContractMonth", None),
                }
            )
            continue
        if asset == "CASH":
            continue
        instrument_key = f"{position.symbol}:{position.con_id}" if position.con_id else position.symbol
        latest = DecisionPacketRepository().latest_for_instrument(resolved, instrument_key)
        holdings.append(
            {
                "symbol": position.symbol,
                "instrument_key": instrument_key,
                "portfolio_weight": float(getattr(position, "portfolio_weight", 0) or 0),
                "outcome": latest.outcome.value if latest else "data_insufficient",
                "priority": latest.priority if latest else "routine",
                "has_decision_packet": latest is not None,
            }
        )
    queue = ResearchQueueService().build_queue(account_id=resolved, holdings=holdings)
    queue["catalysts"] = build_catalyst_calendar(
        symbols=[h["symbol"] for h in holdings[:20]],
        option_positions=option_positions,
    )
    queue["order_generated"] = False
    return queue


@router.get("/change-feed")
def research_change_feed(
    account_id: str | None = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    from app.api.routes.portfolio import _resolve_account_data

    summary, positions = _resolve_account_data(adapter, account_id, principal)
    resolved = summary.account_id
    changes: list[dict[str, Any]] = []
    for position in positions:
        if getattr(position, "asset_class", None) in {"OPT", "FOP", "CASH"}:
            continue
        instrument_key = f"{position.symbol}:{position.con_id}" if position.con_id else position.symbol
        latest = DecisionPacketRepository().latest_for_instrument(resolved, instrument_key)
        if latest is None:
            continue
        previous_weight = None
        payload = latest.model_dump(mode="json") if hasattr(latest, "model_dump") else {}
        scenarios = payload.get("scenarios") or []
        for scenario in scenarios:
            if isinstance(scenario, dict) and scenario.get("scenario_type") == "no_trade":
                previous_weight = scenario.get("current_weight_percent") or scenario.get("proposed_weight_percent")
                break
        fit = (payload.get("lens_ensemble") or {}) if isinstance(payload, dict) else {}
        if previous_weight is None:
            previous_weight = (
                (payload.get("portfolio_fit") or {}).get("weight")
                if isinstance(payload.get("portfolio_fit"), dict)
                else None
            )
        previous = {
            "outcome": latest.previous_outcome.value if latest.previous_outcome else None,
            "portfolio_weight": previous_weight,
            "thesis_status": (payload.get("thesis") or {}).get("status")
            if isinstance(payload.get("thesis"), dict)
            else None,
        }
        current = {
            "outcome": latest.outcome.value,
            "portfolio_weight": float(getattr(position, "portfolio_weight", 0) or 0),
            "blockers": latest.blockers,
            "thesis_status": previous.get("thesis_status"),
            "hard_risk_breach": bool(fit.get("hard_risk_breach")) if isinstance(fit, dict) else False,
        }
        detected = detect_changes(previous, current)
        for item in detected:
            item["symbol"] = position.symbol
            item["instrument_key"] = instrument_key
            item["decision_id"] = latest.decision_id
            changes.append(item)
    return {
        "account_id": resolved,
        "changes": changes,
        "count": len(changes),
        "order_generated": False,
    }


@router.get("/catalysts")
def research_catalysts(
    account_id: str | None = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    from app.api.routes.portfolio import _resolve_account_data

    summary, positions = _resolve_account_data(adapter, account_id, principal)
    symbols = [
        p.symbol
        for p in positions
        if getattr(p, "asset_class", None) not in {"OPT", "FOP", "CASH"}
    ]
    option_positions = [
        {
            "symbol": p.symbol,
            "expiry": getattr(p, "expiry", None) or getattr(p, "lastTradeDateOrContractMonth", None),
        }
        for p in positions
        if getattr(p, "asset_class", None) in {"OPT", "FOP"}
    ]
    events = build_catalyst_calendar(symbols=symbols[:40], option_positions=option_positions)
    # Persist catalysts into the canonical catalysts table (§8.8 / §17).
    try:
        import hashlib

        from app.db.instruments_repository import resolve_instrument
        from app.db.reference_data_repo import save_catalyst

        for event in events:
            sym = str(event.get("symbol") or "").upper()
            if not sym:
                continue
            instrument = resolve_instrument(symbol=sym, con_id=None)
            ctype = str(event.get("catalyst_type") or event.get("event_type") or "catalyst")
            key = f"{instrument.instrument_id}:{ctype}:{event.get('event_date') or event.get('date') or ''}"
            catalyst_id = "cat_" + hashlib.sha256(key.encode()).hexdigest()[:16]
            save_catalyst(catalyst_id, instrument.instrument_id, ctype, event)
    except Exception:  # noqa: BLE001 — persistence must not break the read
        pass
    return {
        "account_id": summary.account_id,
        "events": events,
        "count": len(events),
        "order_generated": False,
    }


@router.get("/candidates/{candidate_id}")
def get_candidate(candidate_id: str) -> dict[str, Any]:
    row = ResearchCandidateRepository().get(candidate_id)
    if not row:
        raise HTTPException(status_code=404, detail="candidate_not_found")
    return row


@router.post("/compare")
def compare(body: CompareRequest) -> dict[str, Any]:
    repo = ResearchCandidateRepository()
    left = repo.get(body.left_candidate_id)
    right = repo.get(body.right_candidate_id)
    if not left or not right:
        raise HTTPException(status_code=404, detail="candidate_not_found")
    return compare_candidates(left, right)


# --- Structured research notes (§8.5) --------------------------------------


@router.get("/notes")
def list_research_notes(
    account_id: str,
    instrument_id: str | None = None,
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    from app.db.research_note_repo import list_notes

    notes = list_notes(account_id, instrument_id=instrument_id)
    return {"account_id": account_id, "count": len(notes), "notes": [n.model_dump(mode="json") for n in notes]}


@router.post("/notes")
def create_research_note(
    body: ResearchNoteCreate,
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    from uuid import uuid4

    from app.db.research_note_repo import save_note
    from app.schemas.research_note import ResearchNote

    note = ResearchNote(note_id=f"note_{uuid4().hex[:12]}", **body.model_dump())
    save_note(note)
    return note.model_dump(mode="json")


@router.get("/notes/{note_id}")
def get_research_note(note_id: str, principal: Principal = Depends(get_current_principal)) -> dict[str, Any]:
    from app.db.research_note_repo import get_note

    note = get_note(note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="note_not_found")
    return note.model_dump(mode="json")


@router.patch("/notes/{note_id}")
def update_research_note(
    note_id: str,
    body: dict[str, Any],
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    from app.db.research_note_repo import get_note, save_note

    note = get_note(note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="note_not_found")
    for field in ("title", "body", "tags", "evidence_links", "note_type"):
        if field in body and body[field] is not None:
            setattr(note, field, body[field])
    save_note(note)
    return note.model_dump(mode="json")
