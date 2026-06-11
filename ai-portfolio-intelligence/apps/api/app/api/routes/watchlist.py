from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel
from app.core.audit import log_audit_action


router = APIRouter(prefix="/watchlist", tags=["watchlist"])
_WATCHLIST = [
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


class WatchlistItem(BaseModel):
    symbol: str
    reason: str
    target_add_price: Optional[float] = None
    target_trim_review_price: Optional[float] = None


@router.get("")
def list_watchlist():
    return _WATCHLIST


@router.post("")
def create_watchlist_item(payload: WatchlistItem):
    item = {"id": len(_WATCHLIST) + 1, **payload.model_dump(), "status": "watch"}
    _WATCHLIST.append(item)
    log_audit_action(
        action="watchlist_item_added",
        object_type="security",
        object_id=payload.symbol.upper(),
        metadata=payload.model_dump()
    )
    return item


@router.put("/{item_id}")
def update_watchlist_item(item_id: int, payload: WatchlistItem):
    for item in _WATCHLIST:
        if item["id"] == item_id:
            item.update(payload.model_dump())
            log_audit_action(
                action="watchlist_item_updated",
                object_type="security",
                object_id=payload.symbol.upper(),
                metadata=payload.model_dump()
            )
            return item
    return {"status": "not_found"}


@router.delete("/{item_id}")
def delete_watchlist_item(item_id: int):
    global _WATCHLIST
    symbol = "UNKNOWN"
    for item in _WATCHLIST:
        if item["id"] == item_id:
            symbol = item["symbol"]
            break
    _WATCHLIST = [item for item in _WATCHLIST if item["id"] != item_id]
    log_audit_action(
        action="watchlist_item_removed",
        object_type="security",
        object_id=symbol.upper()
    )
    return {"status": "deleted"}
