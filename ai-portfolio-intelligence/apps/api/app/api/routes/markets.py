"""Market intelligence API (plan §7 / §19).

Every response carries a data-quality envelope. Indicators without a configured
provider are reported ``unavailable`` — never fabricated. The regime label is
produced by an explainable rule engine, never by an LLM.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.auth_deps import Principal, get_current_principal
from app.api.deps import demo_mode_enabled, get_broker_adapter
from app.db.market_repo import (
    latest_market_regime,
    list_economic_events,
    save_market_regime,
    save_market_snapshot,
)
from app.schemas.market import MarketRegime, MarketSnapshot
from app.services.broker.base import BrokerAdapter
from app.services.market_intelligence.regime import classify_regime
from app.services.market_intelligence.snapshot import build_market_snapshot, derive_dimensions

router = APIRouter(
    prefix="/markets",
    tags=["markets"],
    dependencies=[Depends(get_current_principal)],
)


def _portfolio_context(adapter: BrokerAdapter, principal: Principal):
    """Best-effort portfolio snapshot used as an explicit regime proxy."""
    try:
        from app.api.routes.portfolio import _resolve_account_data

        return _resolve_account_data(adapter, "all", principal)
    except Exception:  # noqa: BLE001
        return None, []


@router.get("/overview", response_model=MarketSnapshot)
def market_overview(
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
) -> MarketSnapshot:
    summary, positions = _portfolio_context(adapter, principal)
    snapshot = build_market_snapshot(
        demo=demo_mode_enabled(), previous=latest_market_regime(), summary=summary, positions=positions
    )
    save_market_snapshot(snapshot)
    if snapshot.regime is not None:
        save_market_regime(snapshot.regime)
    return snapshot


@router.get("/regime", response_model=MarketRegime)
def market_regime(
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
) -> MarketRegime:
    previous = latest_market_regime()
    summary, positions = _portfolio_context(adapter, principal)
    dims, limitations = derive_dimensions(demo=demo_mode_enabled(), summary=summary, positions=positions)
    regime = classify_regime(dims, previous=previous)
    for lim in limitations:
        if lim not in regime.data_limitations:
            regime.data_limitations.append(lim)
    save_market_regime(regime)
    return regime


@router.get("/sectors")
def market_sectors(principal: Principal = Depends(get_current_principal)) -> dict[str, object]:
    return {
        "status": "unavailable",
        "note": "Market-wide sector leadership requires a configured market-data provider; "
        "portfolio sector exposure is available under /portfolio/risk.",
        "sectors": [],
        "data_quality": {"status": "unavailable"},
    }


@router.get("/factors")
def market_factors(principal: Principal = Depends(get_current_principal)) -> dict[str, object]:
    return {
        "status": "unavailable",
        "note": "Factor performance requires a configured factor-return source.",
        "factors": [],
        "data_quality": {"status": "unavailable"},
    }


@router.get("/calendar")
def market_calendar(principal: Principal = Depends(get_current_principal)) -> dict[str, object]:
    events = list_economic_events()
    return {
        "count": len(events),
        "events": [e.model_dump(mode="json") for e in events],
        "data_quality": {
            "status": "available" if events else "empty",
            "note": "Economic and earnings events appear when imported or provider-supplied.",
        },
    }


@router.get("/history")
def market_history(principal: Principal = Depends(get_current_principal)) -> dict[str, object]:
    latest = latest_market_regime()
    return {
        "latest_regime": latest.model_dump(mode="json") if latest else None,
        "data_quality": {"status": "available" if latest else "empty"},
    }
