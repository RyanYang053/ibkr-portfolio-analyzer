from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request

from app.core.config import settings


@dataclass
class _LoginState:
    failures: int = 0
    locked_until: datetime | None = None


_lock = __import__("threading").Lock()
_login_states: dict[str, _LoginState] = {}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _client_key(request: Request, email: str) -> str:
    client = request.client.host if request.client else "unknown"
    return f"{client}:{email.lower()}"


def _load_persistent_state(key: str) -> _LoginState | None:
    from app.db.state_store import get_state_store

    payload = get_state_store().read_json("login_rate_limit", key)
    if not isinstance(payload, dict):
        return None
    locked_until = payload.get("locked_until")
    return _LoginState(
        failures=int(payload.get("failures", 0)),
        locked_until=datetime.fromisoformat(locked_until) if locked_until else None,
    )


def _save_persistent_state(key: str, state: _LoginState) -> None:
    from app.db.state_store import get_state_store

    get_state_store().write_json(
        "login_rate_limit",
        key,
        {
            "failures": state.failures,
            "locked_until": state.locked_until.isoformat() if state.locked_until else None,
        },
    )


def _delete_persistent_state(key: str) -> None:
    from app.db.state_store import get_state_store

    get_state_store().delete("login_rate_limit", key)


def check_login_allowed(request: Request, email: str) -> None:
    key = _client_key(request, email)
    with _lock:
        state = _login_states.get(key) or _load_persistent_state(key)
        if state and state.locked_until and state.locked_until > _utc_now():
            raise HTTPException(
                status_code=429,
                detail="Too many failed login attempts. Try again later.",
            )


def record_login_failure(request: Request, email: str) -> None:
    key = _client_key(request, email)
    with _lock:
        state = _login_states.get(key) or _load_persistent_state(key) or _LoginState()
        state.failures += 1
        if state.failures >= settings.login_max_attempts:
            state.locked_until = _utc_now() + timedelta(minutes=settings.login_lockout_minutes)
        _login_states[key] = state
        _save_persistent_state(key, state)


def clear_login_failures(request: Request, email: str) -> None:
    key = _client_key(request, email)
    with _lock:
        _login_states.pop(key, None)
        _delete_persistent_state(key)
