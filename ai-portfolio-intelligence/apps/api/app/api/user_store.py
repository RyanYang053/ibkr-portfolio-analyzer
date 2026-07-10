from __future__ import annotations

from app.core.config import settings
from app.db.legacy_bridge import read_json_with_legacy, write_json_state

_USERS: dict[str, dict[str, str]] = {}


def _hydrate_users() -> None:
    global _USERS
    if _USERS:
        return
    if settings.persistence_backend == "postgres":
        from app.db.user_repo import load_all_users, upsert_user

        stored = load_all_users()
        if stored:
            _USERS.update(stored)
            return
        legacy = read_json_with_legacy("users", "registry", None, default={})
        if isinstance(legacy, dict) and legacy:
            for email, user in legacy.items():
                if isinstance(user, dict):
                    upsert_user(email, user)
            stored = load_all_users() or {}
            _USERS.update(stored)
            return
    stored = read_json_with_legacy("users", "registry", None, default={})
    if isinstance(stored, dict):
        _USERS.update(stored)


def get_user(email: str) -> dict[str, str] | None:
    _hydrate_users()
    if settings.persistence_backend == "postgres":
        from app.db.user_repo import get_user as get_postgres_user

        user = get_postgres_user(email)
        if user:
            _USERS[user["email"]] = user
            return user
    return _USERS.get(email.lower())


def save_user(email: str, user: dict[str, str]) -> None:
    _hydrate_users()
    normalized = email.lower()
    record = {**user, "email": normalized}
    _USERS[normalized] = record
    if settings.persistence_backend == "postgres":
        from app.db.user_repo import upsert_user

        upsert_user(normalized, record)
        return
    write_json_state("users", "registry", _USERS)


def list_users() -> list[dict[str, str]]:
    _hydrate_users()
    return list(_USERS.values())


def owner_exists() -> bool:
    _hydrate_users()
    return any(user.get("role") == "owner" for user in _USERS.values())


def update_user_role(email: str, role: str) -> dict[str, str] | None:
    _hydrate_users()
    user = _USERS.get(email.lower())
    if not user:
        return None
    user["role"] = role
    save_user(email.lower(), user)
    return user


def bump_token_version(email: str) -> int:
    _hydrate_users()
    user = _USERS.get(email.lower())
    if not user:
        return 0
    version = int(user.get("token_version", "0")) + 1
    user["token_version"] = str(version)
    save_user(email.lower(), user)
    return version


def get_token_version(email: str) -> int:
    user = get_user(email)
    if not user:
        return 0
    return int(user.get("token_version", "0"))
