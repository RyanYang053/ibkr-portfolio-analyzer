from __future__ import annotations

from typing import Optional

from fastapi import HTTPException

from app.core.config import settings
from app.schemas.domain import Position
from app.services.broker.base import BrokerAdapter

CONSOLIDATED_ANALYTICS_UNAVAILABLE = {
    "code": "CONSOLIDATED_ANALYTICS_UNAVAILABLE",
    "message": (
        "Consolidated multi-account analytics are unavailable. "
        "Request a specific account_id for performance, tax, attribution, risk history, and construction proposals."
    ),
    "status": "unavailable",
}

ACCOUNT_ID_REQUIRED_FOR_CONID = {
    "code": "ACCOUNT_ID_REQUIRED_FOR_CONID",
    "message": "account_id is required when resolving a position by con_id.",
    "status": "unavailable",
}


def require_single_account_id(
    account_id: Optional[str],
    summary_account_id: str,
    adapter: BrokerAdapter,
) -> str:
    """Resolve a single account for analytics. Fail closed for true multi-account consolidation."""
    accounts = adapter.get_accounts()
    if not accounts:
        raise HTTPException(status_code=422, detail={"code": "NO_ACCOUNTS", "status": "unavailable"})

    if account_id and account_id not in {"all", "default"}:
        return account_id

    if summary_account_id and summary_account_id not in {"all", "default"}:
        return summary_account_id

    if len(accounts) == 1:
        return accounts[0].id

    raise HTTPException(status_code=422, detail=CONSOLIDATED_ANALYTICS_UNAVAILABLE)


def resolve_portfolio_account_id(
    account_id: Optional[str],
    adapter: BrokerAdapter,
) -> str:
    """Resolve a single account for portfolio reads. Fail closed when ambiguous."""
    return require_single_account_id(account_id, "default", adapter)


def find_portfolio_position(
    symbol: str,
    adapter: BrokerAdapter,
    account_id: Optional[str] = None,
    con_id: Optional[int] = None,
) -> Position | None:
    """Locate a held position by account + conId, or by symbol within a resolved account scope."""
    if con_id is not None:
        if not account_id or account_id in {"all", "default"}:
            raise HTTPException(status_code=422, detail=ACCOUNT_ID_REQUIRED_FOR_CONID)
        try:
            for position in adapter.get_positions(account_id):
                if position.con_id == con_id:
                    return position
        except Exception:
            return None
        return None

    target = symbol.upper().strip()
    account_ids: list[str] = []

    if account_id and account_id not in {"all", "default"}:
        account_ids = [account_id]
    else:
        accounts = adapter.get_accounts()
        if not accounts:
            return None
        if len(accounts) == 1:
            account_ids = [accounts[0].id]
        elif settings.ibkr_account_id:
            account_ids = [settings.ibkr_account_id]
        else:
            return None

    for active_id in account_ids:
        try:
            for position in adapter.get_positions(active_id):
                if position.symbol.upper() == target:
                    return position
                if position.local_symbol and position.local_symbol.upper() == target:
                    return position
        except Exception:
            continue
    return None


def is_symbol_held(
    symbol: str,
    adapter: BrokerAdapter,
    account_id: Optional[str] = None,
    con_id: Optional[int] = None,
) -> bool:
    return find_portfolio_position(symbol, adapter, account_id, con_id) is not None


def is_consolidated_scope(account_id: Optional[str], summary_account_id: str) -> bool:
    if account_id == "all" or summary_account_id == "all":
        return True
    return account_id in (None, "default") and summary_account_id in {"all", "default"}
