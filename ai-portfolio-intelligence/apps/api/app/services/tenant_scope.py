from __future__ import annotations

from app.api.auth_deps import Principal, auth_enforcement_active


def tenant_user_id(principal: Principal) -> str:
    return principal.user_id.lower()


def tenant_account_scope_key(principal: Principal, account_id: str) -> str:
    return f"{tenant_user_id(principal)}:{account_id}"


def tenant_symbol_scope_key(principal: Principal, symbol: str) -> str:
    return f"{tenant_user_id(principal)}:{symbol.upper().strip()}"


def tenant_ai_cache_key(
    principal: Principal,
    account_id: str,
    symbol: str,
    *,
    report_type: str = "stock",
) -> str:
    return f"{tenant_user_id(principal)}:{account_id}:{symbol.upper().strip()}:{report_type}"


def scoped_record_key(user_id: str, *parts: str) -> str:
    return ":".join([user_id.lower(), *[str(part) for part in parts]])


def auth_scoped_defaults_enabled() -> bool:
    return auth_enforcement_active()
