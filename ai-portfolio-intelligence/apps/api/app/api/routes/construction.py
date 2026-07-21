"""Portfolio construction scenarios API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.api.auth_deps import Principal, get_current_principal
from app.api.deps import get_broker_adapter
from app.core.product_contract import ORDER_GENERATED_DEFAULT
from app.db.financial_plan_repo import FinancialPlanRepository
from app.services.broker.base import BrokerAdapter
from app.services.portfolio_construction.replacement_universe import build_replacement_universe
from app.services.portfolio_construction.scenario_service import build_construction_scenarios

router = APIRouter(
    prefix="/construction",
    tags=["construction"],
    dependencies=[Depends(get_current_principal)],
)


def _weights_from_positions(positions) -> tuple[dict[str, float], dict[str, float]]:
    weights: dict[str, float] = {}
    sectors: dict[str, float] = {}
    for position in positions:
        if getattr(position, "asset_class", None) in {"OPT", "FOP", "CASH"}:
            continue
        symbol = position.symbol
        weight = float(getattr(position, "portfolio_weight", 0) or 0)
        weights[symbol] = weights.get(symbol, 0.0) + weight
        sector = getattr(position, "sector", None) or "Unknown"
        sectors[sector] = sectors.get(sector, 0.0) + weight
    return weights, sectors


def _watchlist_symbols() -> list[str]:
    try:
        from app.db.state_store import get_state_store

        store = get_state_store()
        payload = store.read_json("watchlist", "items", default={"items": []}) or {}
        items = payload.get("items") or payload.get("symbols") or []
        symbols: list[str] = []
        for item in items:
            if isinstance(item, str):
                symbols.append(item.upper())
            elif isinstance(item, dict) and item.get("symbol"):
                symbols.append(str(item["symbol"]).upper())
        return symbols
    except Exception:
        return []


@router.get("/scenarios")
def construction_scenarios(
    account_id: str | None = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    from app.api.routes.portfolio import _resolve_account_data

    summary, positions = _resolve_account_data(adapter, account_id, principal)
    resolved = summary.account_id
    weights, sectors = _weights_from_positions(positions)
    cash_percent = 0.0
    if summary.net_liquidation:
        cash_percent = float(summary.cash) / abs(float(summary.net_liquidation)) * 100.0
    weights = {**weights, "CASH": cash_percent}

    plan = FinancialPlanRepository().latest()
    plan_payload = plan.model_dump(mode="json") if plan else {}
    universe = build_replacement_universe(
        plan=plan_payload,
        watchlist_symbols=_watchlist_symbols(),
        held_symbols=list(weights.keys()),
    )
    result = build_construction_scenarios(
        account_id=resolved,
        current_weights=weights,
        sector_weights=sectors,
        cash_percent=cash_percent,
        core_etf=universe.get("core_etf"),
    )
    result["replacement_universe"] = universe
    result["order_generated"] = ORDER_GENERATED_DEFAULT
    result["cash_percent"] = cash_percent
    return result


@router.get("/replacement-universe")
def replacement_universe(
    account_id: str | None = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    from app.api.routes.portfolio import _resolve_account_data

    summary, positions = _resolve_account_data(adapter, account_id, principal)
    weights, _sectors = _weights_from_positions(positions)
    plan = FinancialPlanRepository().latest()
    universe = build_replacement_universe(
        plan=plan.model_dump(mode="json") if plan else {},
        watchlist_symbols=_watchlist_symbols(),
        held_symbols=list(weights.keys()),
    )
    universe["account_id"] = summary.account_id
    return universe
