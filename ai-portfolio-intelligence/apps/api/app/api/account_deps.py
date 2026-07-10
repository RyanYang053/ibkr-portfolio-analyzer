from __future__ import annotations

from fastapi import Depends, HTTPException

from app.api.account_access_store import list_accessible_accounts, user_has_account_access
from app.api.auth_deps import Principal, get_current_principal


def require_account_access(
    account_id: str,
    principal: Principal = Depends(get_current_principal),
) -> str:
    if principal.role == "owner":
        accessible = list_accessible_accounts(principal.user_id)
        if not accessible or account_id in accessible:
            return account_id
    elif user_has_account_access(principal.user_id, account_id):
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
    if principal.role == "owner":
        accessible = list_accessible_accounts(principal.user_id)
        if not accessible:
            return account_ids
        return [account_id for account_id in account_ids if account_id in accessible]
    accessible = set(list_accessible_accounts(principal.user_id))
    return [account_id for account_id in account_ids if account_id in accessible]


def ensure_account_access(account_id: str, principal: Principal) -> None:
    require_account_access(account_id, principal)
