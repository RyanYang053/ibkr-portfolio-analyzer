"""Screener API (plan §8.2 / §19).

A screen surfaces research candidates from the account universe (holdings +
watchlist). No result is a buy recommendation; every result carries the criteria
it matched and the data it was missing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth_deps import Principal, get_current_principal
from app.api.deps import demo_mode_enabled, get_broker_adapter
from app.db.instruments_repository import resolve_instrument
from app.db.screener_repo import (
    get_definition,
    get_result,
    get_run,
    list_definitions,
    save_definition,
    save_run,
)
from app.domain.instrument import instrument_key
from app.schemas.screener import ScreenDefinition, ScreenDefinitionCreate
from app.services.broker.base import BrokerAdapter
from app.services.screening.engine import run_screen

router = APIRouter(prefix="/screeners", tags=["screener"], dependencies=[Depends(get_current_principal)])

_NUMERIC_FIELDS = (
    "revenue_growth_yoy",
    "gross_margin",
    "operating_margin",
    "free_cash_flow",
    "fcf_yield",
    "pe_forward",
    "ev_sales",
    "total_debt",
    "cash",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _metric_resolver(demo: bool):
    from app.services.fundamentals.snapshot_store import list_snapshot_records

    def resolve(symbol: str) -> dict[str, float | None]:
        records = list_snapshot_records(symbol, include_synthetic_demo=demo)
        if not records:
            return {}
        latest = sorted(records, key=lambda r: r.as_of_date)[-1].snapshot
        return {field: getattr(latest, field, None) for field in _NUMERIC_FIELDS}

    return resolve


def _build_universe(
    definition: ScreenDefinition, adapter: BrokerAdapter, account_id: str, principal: Principal
) -> tuple[list[tuple[str, str]], set[str], set[str]]:
    owned: set[str] = set()
    universe: dict[str, str] = {}
    if definition.universe in {"holdings_and_watchlist", "holdings"}:
        try:
            from app.api.routes.portfolio import _resolve_account_data

            _summary, positions = _resolve_account_data(adapter, account_id, principal)
            for pos in positions:
                if getattr(pos, "asset_class", None) in {"CASH"}:
                    continue
                sym = pos.symbol.upper()
                owned.add(sym)
                universe[sym] = instrument_key(sym, pos.con_id)
        except Exception:  # noqa: BLE001
            pass
    watchlist: set[str] = set()
    if definition.universe in {"holdings_and_watchlist", "watchlist"}:
        try:
            from app.services.watchlist_store import load_user_watchlist

            for item in load_user_watchlist(getattr(principal, "user_id", "local-owner")):
                sym = str(item.get("symbol") or "").upper()
                if sym:
                    watchlist.add(sym)
                    universe.setdefault(sym, instrument_key(sym, None))
        except Exception:  # noqa: BLE001
            pass
    return sorted(universe.items()), owned, watchlist


@router.get("")
def list_screens(account_id: str, principal: Principal = Depends(get_current_principal)) -> dict[str, object]:
    defs = list_definitions(account_id)
    return {"account_id": account_id, "count": len(defs), "screeners": [d.model_dump(mode="json") for d in defs]}


@router.post("")
def create_screen(
    account_id: str,
    body: ScreenDefinitionCreate,
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    defn = ScreenDefinition(
        screen_id=f"scr_{uuid4().hex[:12]}",
        name=body.name,
        filters=body.filters,
        universe=body.universe,
        created_at=_now(),
    )
    save_definition(defn, account_id)
    return defn.model_dump(mode="json")


@router.patch("/{screen_id}")
def update_screen(
    screen_id: str,
    account_id: str,
    body: ScreenDefinitionCreate,
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    defn = get_definition(screen_id)
    if defn is None:
        raise HTTPException(status_code=404, detail=f"Unknown screen: {screen_id}")
    defn.name = body.name
    defn.filters = body.filters
    defn.universe = body.universe
    save_definition(defn, account_id)
    return defn.model_dump(mode="json")


@router.post("/{screen_id}/run")
def run_screen_endpoint(
    screen_id: str,
    account_id: str,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    defn = get_definition(screen_id)
    if defn is None:
        raise HTTPException(status_code=404, detail=f"Unknown screen: {screen_id}")
    universe, owned, watchlist = _build_universe(defn, adapter, account_id, principal)
    run = run_screen(
        defn,
        account_id=account_id,
        universe=universe,
        metric_resolver=_metric_resolver(demo_mode_enabled()),
        owned_symbols=owned,
        watchlist_symbols=watchlist,
    )
    save_run(run)
    return run.model_dump(mode="json")


@router.get("/runs/{run_id}")
def get_run_endpoint(run_id: str, principal: Principal = Depends(get_current_principal)) -> dict[str, object]:
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Unknown screen run: {run_id}")
    return run.model_dump(mode="json")


@router.post("/results/{result_id}/promote")
def promote_result(
    result_id: str,
    account_id: str,
    target: str = "research_queue",
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    """Promote a candidate to the research queue or watchlist. Never a buy action."""
    result = get_result(result_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Unknown screen result: {result_id}")
    resolve_instrument(symbol=result.symbol, con_id=None)
    promoted_to = target
    if target == "research_queue":
        try:
            from app.db.research_candidate_repo import ResearchCandidateRepository

            ResearchCandidateRepository().save_candidate(
                {
                    "candidate_id": f"cand_{uuid4().hex[:12]}",
                    "account_id": account_id,
                    "instrument_key": result.instrument_id,
                    "symbol": result.symbol,
                    "reason": "promoted_from_screener",
                    "priority": "routine",
                }
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"promotion failed: {exc}") from exc
    else:
        promoted_to = "unsupported_target"
    return {"result_id": result_id, "symbol": result.symbol, "promoted_to": promoted_to, "order_generated": False}
