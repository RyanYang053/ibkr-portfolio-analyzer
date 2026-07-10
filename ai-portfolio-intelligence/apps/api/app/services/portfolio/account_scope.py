from __future__ import annotations

from typing import Optional

from fastapi import HTTPException

from app.services.broker.base import BrokerAdapter


CONSOLIDATED_ANALYTICS_UNAVAILABLE = {
    "code": "CONSOLIDATED_ANALYTICS_UNAVAILABLE",
    "message": (
        "Consolidated multi-account analytics are unavailable. "
        "Request a specific account_id for performance, tax, attribution, risk history, and construction proposals."
    ),
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

    if summary_account_id not in {"all", "default"}:
        return summary_account_id

    if len(accounts) == 1:
        return accounts[0].id

    raise HTTPException(status_code=422, detail=CONSOLIDATED_ANALYTICS_UNAVAILABLE)


def is_consolidated_scope(account_id: Optional[str], summary_account_id: str) -> bool:
    if account_id == "all" or summary_account_id == "all":
        return True
    return account_id in (None, "default") and summary_account_id in {"all", "default"}
