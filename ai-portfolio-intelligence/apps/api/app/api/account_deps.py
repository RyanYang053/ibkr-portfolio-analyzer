from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException

from app.api.account_access_store import list_accessible_accounts, user_has_account_access
from app.api.auth_deps import Principal, auth_enforcement_active, get_current_principal
from app.api.deps import get_broker_adapter
from app.services.broker.base import BrokerAdapter

WILDCARD_ACCOUNT = "*"
SCHEDULER_ALL_ACCOUNTS = "__all__"

ACCOUNT_SELECTION_REQUIRED = {
    "code": "ACCOUNT_SELECTION_REQUIRED",
    "message": "account_id is required when multiple broker accounts are accessible.",
    "status": "unavailable",
}


def _accessible_account_ids(principal: Principal) -> list[str]:
    if not auth_enforcement_active() and principal.user_id == "local-dev":
        return [WILDCARD_ACCOUNT]
    return list_accessible_accounts(principal.user_id)


def _allowed_broker_accounts(adapter: BrokerAdapter, principal: Principal) -> list[str]:
    broker_ids = [account.id for account in adapter.get_accounts()]
    accessible = _accessible_account_ids(principal)
    if WILDCARD_ACCOUNT in accessible:
        return broker_ids
    return [account_id for account_id in broker_ids if account_id in accessible]


def resolve_authorized_account_ids(
    adapter: BrokerAdapter,
    principal: Principal,
    requested_account_id: Optional[str] = None,
) -> list[str]:
    allowed = _allowed_broker_accounts(adapter, principal)

    if requested_account_id and requested_account_id not in {"all", "default"}:
        if requested_account_id not in allowed:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "ACCOUNT_ACCESS_DENIED",
                    "message": f"User does not have access to account {requested_account_id}.",
                },
            )
        return [requested_account_id]

    if requested_account_id == "all":
        if not allowed:
            raise HTTPException(status_code=404, detail="No accessible accounts")
        return allowed

    if len(allowed) == 1:
        return allowed

    if not allowed:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "ACCOUNT_ACCESS_DENIED",
                "message": "No broker accounts are accessible for this user.",
            },
        )

    raise HTTPException(status_code=422, detail=ACCOUNT_SELECTION_REQUIRED)


def resolve_authorized_account_id(
    account_id: Optional[str],
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
) -> str:
    return resolve_authorized_account_ids(adapter, principal, account_id)[0]


def require_account_access(
    account_id: str,
    principal: Principal = Depends(get_current_principal),
) -> str:
    accessible = _accessible_account_ids(principal)
    if WILDCARD_ACCOUNT in accessible or account_id in accessible:
        return account_id
    raise HTTPException(
        status_code=403,
        detail={
            "code": "ACCOUNT_ACCESS_DENIED",
            "message": f"User does not have access to account {account_id}.",
        },
    )


def filter_accounts_for_principal(
    account_ids: list[str],
    principal: Principal,
) -> list[str]:
    accessible = _accessible_account_ids(principal)
    if WILDCARD_ACCOUNT in accessible:
        return account_ids
    allowed = set(accessible)
    return [account_id for account_id in account_ids if account_id in allowed]


def ensure_account_access(account_id: str, principal: Principal) -> None:
    require_account_access(account_id, principal)
