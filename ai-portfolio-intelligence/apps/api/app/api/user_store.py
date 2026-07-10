from __future__ import annotations

_USERS: dict[str, dict[str, str]] = {}


def get_user(email: str) -> dict[str, str] | None:
    return _USERS.get(email)


def save_user(email: str, user: dict[str, str]) -> None:
    _USERS[email] = user
