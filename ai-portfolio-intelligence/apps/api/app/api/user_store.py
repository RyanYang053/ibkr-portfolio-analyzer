from __future__ import annotations

from app.db.legacy_bridge import read_json_with_legacy, write_json_state

_USERS: dict[str, dict[str, str]] = {}


def _hydrate_users() -> None:
    global _USERS
    if _USERS:
        return
    stored = read_json_with_legacy("users", "registry", None, default={})
    if isinstance(stored, dict):
        _USERS.update(stored)


def get_user(email: str) -> dict[str, str] | None:
    _hydrate_users()
    return _USERS.get(email)


def save_user(email: str, user: dict[str, str]) -> None:
    _hydrate_users()
    _USERS[email] = user
    write_json_state("users", "registry", _USERS)
