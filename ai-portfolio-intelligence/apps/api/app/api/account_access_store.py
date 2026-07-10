from __future__ import annotations

from app.core.config import settings
from app.db.legacy_bridge import read_json_with_legacy, write_json_state

_ACCESS: dict[str, list[str]] = {}


def _hydrate() -> None:
    global _ACCESS
    if _ACCESS:
        return
    if settings.persistence_backend == "postgres":
        from app.db.account_access_repo import grant_account_access, load_all_access

        stored = load_all_access()
        if stored:
            _ACCESS.update(stored)
            return
        legacy = read_json_with_legacy("users", "account_access", None, default={})
        if isinstance(legacy, dict) and legacy:
            for email, accounts in legacy.items():
                if not isinstance(accounts, list):
                    continue
                for account_id in accounts:
                    grant_account_access(email, str(account_id))
            stored = load_all_access() or {}
            _ACCESS.update(stored)
            return
    stored = read_json_with_legacy("users", "account_access", None, default={})
    if isinstance(stored, dict):
        _ACCESS.update({email: list(accounts) for email, accounts in stored.items()})


def _persist() -> None:
    if settings.persistence_backend == "postgres":
        return
    write_json_state("users", "account_access", _ACCESS)


def list_accessible_accounts(user_email: str) -> list[str]:
    _hydrate()
    if settings.persistence_backend == "postgres":
        from app.db.account_access_repo import list_accessible_accounts as list_postgres_accounts

        accounts = list_postgres_accounts(user_email)
        if accounts is not None:
            return accounts
    return list(_ACCESS.get(user_email.lower(), []))


def grant_account_access(user_email: str, account_id: str) -> None:
    _hydrate()
    key = user_email.lower()
    accounts = set(_ACCESS.get(key, []))
    accounts.add(account_id)
    _ACCESS[key] = sorted(accounts)
    if settings.persistence_backend == "postgres":
        from app.db.account_access_repo import grant_account_access as grant_postgres_access

        grant_postgres_access(key, account_id)
        return
    _persist()


def revoke_account_access(user_email: str, account_id: str) -> None:
    _hydrate()
    key = user_email.lower()
    accounts = [value for value in _ACCESS.get(key, []) if value != account_id]
    if accounts:
        _ACCESS[key] = accounts
    else:
        _ACCESS.pop(key, None)
    if settings.persistence_backend == "postgres":
        from app.db.account_access_repo import revoke_account_access as revoke_postgres_access

        revoke_postgres_access(key, account_id)
        return
    _persist()


def user_has_account_access(user_email: str, account_id: str) -> bool:
    return account_id in list_accessible_accounts(user_email)
