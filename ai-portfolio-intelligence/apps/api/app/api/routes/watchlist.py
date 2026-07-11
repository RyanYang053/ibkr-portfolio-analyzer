from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth_deps import Principal, get_current_principal, require_scope
from app.core.audit import log_audit_action
from app.services import watchlist_store
from app.services.tenant_scope import tenant_user_id

router = APIRouter(
    prefix="/watchlist",
    tags=["watchlist"],
    dependencies=[Depends(get_current_principal)],
)


class WatchlistItem(BaseModel):
    symbol: str
    reason: str
    target_add_price: Optional[float] = None
    target_trim_review_price: Optional[float] = None


@router.get("")
def list_watchlist(principal: Principal = Depends(get_current_principal)):
    return watchlist_store.load_user_watchlist(tenant_user_id(principal))


@router.post("", dependencies=[Depends(require_scope("portfolio:write"))])
def create_watchlist_item(payload: WatchlistItem, principal: Principal = Depends(get_current_principal)):
    user_id = tenant_user_id(principal)
    watchlist = watchlist_store.load_user_watchlist(user_id)
    item = {"id": len(watchlist) + 1, **payload.model_dump(), "status": "watch"}
    watchlist.append(item)
    watchlist_store.save_user_watchlist(user_id, watchlist)
    log_audit_action(
        action="watchlist_item_added",
        object_type="security",
        object_id=payload.symbol.upper(),
        actor_id=principal.user_id,
        metadata=payload.model_dump(),
    )
    return item


@router.put("/{item_id}", dependencies=[Depends(require_scope("portfolio:write"))])
def update_watchlist_item(
    item_id: int,
    payload: WatchlistItem,
    principal: Principal = Depends(get_current_principal),
):
    user_id = tenant_user_id(principal)
    watchlist = watchlist_store.load_user_watchlist(user_id)
    for item in watchlist:
        if item["id"] == item_id:
            item.update(payload.model_dump())
            watchlist_store.save_user_watchlist(user_id, watchlist)
            log_audit_action(
                action="watchlist_item_updated",
                object_type="security",
                object_id=payload.symbol.upper(),
                actor_id=principal.user_id,
                metadata=payload.model_dump(),
            )
            return item
    return {"status": "not_found"}


@router.delete("/{item_id}", dependencies=[Depends(require_scope("portfolio:write"))])
def delete_watchlist_item(item_id: int, principal: Principal = Depends(get_current_principal)):
    user_id = tenant_user_id(principal)
    watchlist = watchlist_store.load_user_watchlist(user_id)
    symbol = "UNKNOWN"
    for item in watchlist:
        if item["id"] == item_id:
            symbol = item["symbol"]
            break
    watchlist = [item for item in watchlist if item["id"] != item_id]
    watchlist_store.save_user_watchlist(user_id, watchlist)
    log_audit_action(
        action="watchlist_item_removed",
        object_type="security",
        object_id=symbol.upper(),
        actor_id=principal.user_id,
    )
    return {"status": "deleted"}
