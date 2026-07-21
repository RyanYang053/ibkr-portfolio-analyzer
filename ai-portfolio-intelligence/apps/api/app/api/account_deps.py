from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException

from app.api.auth_deps import Principal, auth_enforcement_active, get_current_principal
from app.api.deps import get_broker_adapter
from app.core.config import is_desktop_local
from app.services.broker.base import BrokerAdapter

WILDCARD_ACCOUNT = "*"
SCHEDULER_ALL_ACCOUNTS = "__all__"
SETTINGS_FALLBACK_ACCOUNT = "default"

ACCOUNT_SELECTION_REQUIRED = {
    "code": "ACCOUNT_SELECTION_REQUIRED",
    "message": "account_id is required when multiple broker accounts are accessible.",
    "status": "unavailable",
}


def _accessible_account_ids(principal: Principal) -> list[str]:
    # Local single-owner product: there are no multi-user ACLs, so every
    # principal has full (wildcard) access to whatever accounts the broker
    # exposes. Account scoping below still honors an explicitly requested id.
    return [WILDCARD_ACCOUNT]


def _known_account_ids_without_live_broker(adapter: BrokerAdapter) -> list[str]:
    """Prefer cached/config account IDs so Settings never blocks on IB sockets."""
    cached = getattr(adapter, "list_cached_accounts", None)
    if callable(cached):
        accounts = cached()
        if accounts:
            return [account.id for account in accounts]

    try:
        from app.services.broker.ibkr_readonly import get_runtime_ibkr_config

        configured = get_runtime_ibkr_config().get("account_id")
        if configured:
            return [str(configured)]
    except Exception:
        pass
    return []


def _allowed_broker_accounts(
    adapter: BrokerAdapter,
    principal: Principal,
    *,
    live: bool = True,
) -> list[str]:
    accessible = _accessible_account_ids(principal)
    broker_ids = _known_account_ids_without_live_broker(adapter)

    if not broker_ids and live:
        broker_ids = [account.id for account in adapter.get_accounts()]

    if not broker_ids and not live:
        # Profile/policy/settings can still load against a local default scope.
        broker_ids = [SETTINGS_FALLBACK_ACCOUNT]

    if WILDCARD_ACCOUNT in accessible:
        return broker_ids

    filtered = [account_id for account_id in broker_ids if account_id in accessible]
    if filtered:
        return filtered

    # Auth-disabled environments (desktop / local) must not block Settings on IB.
    if not live and not auth_enforcement_active():
        return broker_ids if broker_ids else [SETTINGS_FALLBACK_ACCOUNT]
    return filtered


def resolve_authorized_account_ids(
    adapter: BrokerAdapter,
    principal: Principal,
    requested_account_id: Optional[str] = None,
    *,
    live: bool = True,
) -> list[str]:
    allowed = _allowed_broker_accounts(adapter, principal, live=live)
    accessible = _accessible_account_ids(principal)

    if requested_account_id and requested_account_id not in {"all", "default"}:
        if requested_account_id in allowed:
            return [requested_account_id]
        if WILDCARD_ACCOUNT in accessible:
            return [requested_account_id]
        if not live:
            # One live discovery pass for an explicitly requested account.
            allowed = _allowed_broker_accounts(adapter, principal, live=True)
            if requested_account_id in allowed:
                return [requested_account_id]
        raise HTTPException(
            status_code=403,
            detail={
                "code": "ACCOUNT_ACCESS_DENIED",
                "message": f"User does not have access to account {requested_account_id}.",
            },
        )

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

    # Desktop has no login ACL: omit account_id → consolidated "all accounts" view.
    if is_desktop_local() and not requested_account_id:
        return allowed

    raise HTTPException(status_code=422, detail=ACCOUNT_SELECTION_REQUIRED)


def resolve_authorized_account_id(
    account_id: Optional[str],
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
) -> str:
    """Return one concrete broker account id (first when scope is consolidated).

    Prefer resolve_portfolio_scope_id / resolve_authorized_account_ids when the
    caller must honor Consolidated View (`all`) instead of a single account.
    """
    return resolve_authorized_account_ids(adapter, principal, account_id)[0]


def resolve_portfolio_scope_id(
    account_id: Optional[str],
    adapter: BrokerAdapter,
    principal: Principal,
) -> str:
    """Return `all` for multi-account consolidated scope, else the single account id."""
    allowed = resolve_authorized_account_ids(adapter, principal, account_id)
    if len(allowed) > 1:
        return "all"
    return allowed[0]


def resolve_settings_account_id(
    account_id: Optional[str],
    adapter: BrokerAdapter,
    principal: Principal,
) -> str:
    """Resolve account for profile/policy without opening a live IB connection."""
    return resolve_authorized_account_ids(adapter, principal, account_id, live=False)[0]


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
