from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.api.auth_deps import get_current_principal, require_scope
from app.core.audit import log_audit_action
from app.db.legacy_bridge import read_json_with_legacy, write_json_state


router = APIRouter(
    prefix="/watchlist",
    tags=["watchlist"],
    dependencies=[Depends(get_current_principal)],
)

_DEFAULT_WATCHLIST = [
    {
        "id": 1,
        "symbol": "AAPL",
        "reason": "Monitoring consumer hardware cyclicality and AI integration features in iOS.",
        "target_add_price": 185.00,
        "target_trim_review_price": 240.00,
        "status": "watch"
    },
    {
        "id": 2,
        "symbol": "NVDA",
        "reason": "Tracking global AI data center capital expenditures and Blackwell graphics architecture launch cadence.",
        "target_add_price": 110.00,
        "target_trim_review_price": 160.00,
        "status": "watch"
    },
    {
        "id": 3,
        "symbol": "TSLA",
        "reason": "Awaiting vehicle gross margin recovery, energy storage expansion, and FSD hardware updates.",
        "target_add_price": 165.00,
        "target_trim_review_price": 260.00,
        "status": "watch"
    }
]


def _load_watchlist() -> list[dict]:
    items = read_json_with_legacy("watchlist", "items", None, default=None)
    if isinstance(items, list) and items:
        return items
    write_json_state("watchlist", "items", _DEFAULT_WATCHLIST)
    return list(_DEFAULT_WATCHLIST)


def _save_watchlist(items: list[dict]) -> None:
    write_json_state("watchlist", "items", items)


class WatchlistItem(BaseModel):
    symbol: str
    reason: str
    target_add_price: Optional[float] = None
    target_trim_review_price: Optional[float] = None


@router.get("")
def list_watchlist():
    return _load_watchlist()


@router.post("", dependencies=[Depends(require_scope("portfolio:write"))])
def create_watchlist_item(payload: WatchlistItem):
    watchlist = _load_watchlist()
    item = {"id": len(watchlist) + 1, **payload.model_dump(), "status": "watch"}
    watchlist.append(item)
    _save_watchlist(watchlist)
    log_audit_action(
        action="watchlist_item_added",
        object_type="security",
        object_id=payload.symbol.upper(),
        metadata=payload.model_dump()
    )
    return item


@router.put("/{item_id}", dependencies=[Depends(require_scope("portfolio:write"))])
def update_watchlist_item(item_id: int, payload: WatchlistItem):
    watchlist = _load_watchlist()
    for item in watchlist:
        if item["id"] == item_id:
            item.update(payload.model_dump())
            _save_watchlist(watchlist)
            log_audit_action(
                action="watchlist_item_updated",
                object_type="security",
                object_id=payload.symbol.upper(),
                metadata=payload.model_dump()
            )
            return item
    return {"status": "not_found"}


@router.delete("/{item_id}", dependencies=[Depends(require_scope("portfolio:write"))])
def delete_watchlist_item(item_id: int):
    watchlist = _load_watchlist()
    symbol = "UNKNOWN"
    for item in watchlist:
        if item["id"] == item_id:
            symbol = item["symbol"]
            break
    watchlist = [item for item in watchlist if item["id"] != item_id]
    _save_watchlist(watchlist)
    log_audit_action(
        action="watchlist_item_removed",
        object_type="security",
        object_id=symbol.upper()
    )
    return {"status": "deleted"}
