from __future__ import annotations

from app.core.config import settings
from app.db.legacy_bridge import read_json_with_legacy, write_json_state

_USERS: dict[str, dict[str, str]] = {}


def _hydrate_users() -> None:
    global _USERS
    if _USERS:
        return
    if settings.persistence_backend == "postgres":
        return
    stored = read_json_with_legacy("users", "registry", None, default={})
    if isinstance(stored, dict):
        _USERS.update(stored)


def get_user(email: str) -> dict[str, str] | None:
    normalized = email.lower()

    if settings.persistence_backend == "postgres":
        from app.db.user_repo import get_user as get_postgres_user

        return get_postgres_user(normalized)

    _hydrate_users()
    return _USERS.get(normalized)


def save_user(email: str, user: dict[str, str]) -> None:
    normalized = email.lower()
    record = {**user, "email": normalized}

    if settings.persistence_backend == "postgres":
        from app.db.user_repo import upsert_user

        upsert_user(normalized, record)
        return

    _hydrate_users()
    _USERS[normalized] = record
    write_json_state("users", "registry", _USERS)


def list_users() -> list[dict[str, str]]:
    if settings.persistence_backend == "postgres":
        from app.db.user_repo import load_all_users

        return list((load_all_users() or {}).values())

    _hydrate_users()
    return list(_USERS.values())


def owner_exists() -> bool:
    if settings.persistence_backend == "postgres":
        from app.db.user_repo import owner_exists as postgres_owner_exists

        return postgres_owner_exists()

    _hydrate_users()
    return any(user.get("role") == "owner" for user in _USERS.values())


def update_user_role(email: str, role: str) -> dict[str, str] | None:
    if settings.persistence_backend == "postgres":
        from app.db.user_repo import update_user_role as postgres_update_role

        return postgres_update_role(email, role)

    _hydrate_users()
    user = _USERS.get(email.lower())
    if not user:
        return None
    user["role"] = role
    save_user(email.lower(), user)
    return user


def bump_token_version(email: str) -> int:
    if settings.persistence_backend == "postgres":
        from app.db.user_repo import bump_token_version as postgres_bump

        return postgres_bump(email)

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
