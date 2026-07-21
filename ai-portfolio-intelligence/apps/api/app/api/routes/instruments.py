"""Canonical instrument reference API (plan §19 /instruments).

The universal security workspace is organized around the instrument, not the
position, so these endpoints resolve owned AND unowned securities.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.account_deps import resolve_authorized_account_ids
from app.api.auth_deps import Principal, get_current_principal
from app.api.deps import get_broker_adapter
from app.db.instruments_repository import (
    get_instrument,
    resolve_instrument,
    search_instruments,
)
from app.domain.instrument import instrument_key
from app.schemas.instrument import (
    InstrumentOverview,
    InstrumentRecord,
    InstrumentSearchResult,
)
from app.services.broker.base import BrokerAdapter

router = APIRouter(
    prefix="/instruments",
    tags=["instruments"],
    dependencies=[Depends(get_current_principal)],
)


def _account_ids(adapter: BrokerAdapter, principal: Principal) -> list[str]:
    try:
        return list(resolve_authorized_account_ids(adapter, principal, "all"))
    except Exception:  # noqa: BLE001
        return []


def _register_holdings(adapter: BrokerAdapter, account_id: str | None, principal: Principal) -> None:
    """Ensure every current holding has a canonical instrument record."""
    from app.api.routes.portfolio import _resolve_account_data

    try:
        _summary, positions = _resolve_account_data(adapter, account_id, principal)
    except Exception:  # noqa: BLE001 — reference registration must not break lookup
        return
    for position in positions:
        resolve_instrument(
            symbol=position.symbol,
            con_id=position.con_id,
            name=position.company_name or None,
            asset_class=position.asset_class or None,
            currency=position.currency or None,
            exchange=position.exchange or None,
            sector=position.sector or None,
            industry=position.industry or None,
            is_etf=bool(position.is_etf),
        )


@router.get("/search", response_model=InstrumentSearchResult)
def instrument_search(
    q: str,
    limit: int = 25,
    account_id: str | None = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
) -> InstrumentSearchResult:
    query = (q or "").strip()
    if not query:
        raise HTTPException(status_code=422, detail="query 'q' is required")
    _register_holdings(adapter, account_id, principal)
    results = search_instruments(query, limit=max(1, min(limit, 100)))
    return InstrumentSearchResult(query=query, count=len(results), instruments=results)


def _split_instrument_id(instrument_id: str) -> tuple[str, int | None]:
    symbol, _, con = instrument_id.partition(":")
    con_id: int | None = None
    if con:
        try:
            con_id = int(con)
        except ValueError:
            con_id = None
    return symbol.strip().upper(), con_id


@router.get("/{instrument_id}/overview", response_model=InstrumentOverview)
def instrument_overview(
    instrument_id: str,
    account_id: str | None = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
) -> InstrumentOverview:
    """Aggregate the Overview tab (§5.1) for any security, owned or not."""
    symbol, con_id = _split_instrument_id(instrument_id)
    if not symbol:
        raise HTTPException(status_code=422, detail="invalid instrument_id")

    record = get_instrument(instrument_id) or resolve_instrument(symbol=symbol, con_id=con_id)

    # --- position + market (degrade independently) ---
    market: dict[str, object] = {"status": "unavailable", "reason": "no_position_or_quote_source"}
    position_payload: dict[str, object] = {"status": "not_owned"}
    position_status = "not_owned"
    try:
        from app.services.portfolio.account_scope import find_portfolio_position

        held = None
        if account_id and account_id not in {"all", "default"}:
            held = find_portfolio_position(symbol, adapter, account_id, con_id)
        else:
            for acct in _account_ids(adapter, principal):
                held = find_portfolio_position(symbol, adapter, acct, con_id)
                if held is not None:
                    account_id = acct
                    break
        if held is not None:
            position_status = "owned"
            position_payload = {
                "status": "owned",
                "quantity": held.quantity,
                "market_value": held.market_value,
                "unrealized_pnl": held.unrealized_pnl,
                "portfolio_weight": held.portfolio_weight,
                "avg_cost": held.avg_cost,
                "account_id": account_id,
            }
            market = {
                "status": "available",
                "price": held.market_price,
                "currency": held.currency,
                "as_of": held.updated_at.isoformat() if held.updated_at else None,
                "source": held.price_source,
            }
            # Persist the observed quote into the canonical quotes table (§17).
            try:
                from app.db.reference_data_repo import save_quote

                save_quote(record.instrument_id, {k: v for k, v in market.items() if k != "status"})
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001 — section degrades, page does not fail
        position_payload = {"status": "unavailable"}

    # --- latest decision packet ---
    decision: dict[str, object] = {"status": "none"}
    try:
        from app.db.decision_packet_repo import DecisionPacketRepository

        packet = None
        for acct in ([account_id] if account_id else []) or _account_ids(adapter, principal):
            packet = DecisionPacketRepository().latest_for_instrument(str(acct), instrument_id)
            if packet is not None:
                break
        if packet is not None:
            decision = {
                "status": "available",
                "decision_id": packet.decision_id,
                "outcome": packet.outcome.value if hasattr(packet.outcome, "value") else str(packet.outcome),
                "priority": packet.priority,
                "confidence_status": packet.confidence_status,
                "next_review_date": str(packet.next_review_date) if packet.next_review_date else None,
                "top_risks": list(packet.blockers or [])[:5],
                "as_of": packet.as_of.isoformat() if packet.as_of else None,
            }
    except Exception:  # noqa: BLE001
        decision = {"status": "unavailable"}

    return InstrumentOverview(
        instrument=record,
        position_status=position_status,
        market=market,
        position=position_payload,
        decision=decision,
        data_quality={
            "status": "available",
            "market": market.get("status"),
            "position": position_payload.get("status"),
            "decision": decision.get("status"),
        },
    )


@router.get("/{instrument_id}", response_model=InstrumentRecord)
def instrument_detail(
    instrument_id: str,
    account_id: str | None = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
) -> InstrumentRecord:
    record = get_instrument(instrument_id)
    if record is not None:
        return record
    # Not yet in the master — try to register it from current holdings.
    _register_holdings(adapter, account_id, principal)
    record = get_instrument(instrument_id)
    if record is not None:
        return record
    # A bare-symbol id with no position is still a valid (provisional) instrument.
    symbol = instrument_id.split(":", 1)[0].strip().upper()
    if symbol and instrument_key(symbol, None) == instrument_id:
        return resolve_instrument(symbol=symbol, con_id=None)
    raise HTTPException(status_code=404, detail=f"Unknown instrument: {instrument_id}")
