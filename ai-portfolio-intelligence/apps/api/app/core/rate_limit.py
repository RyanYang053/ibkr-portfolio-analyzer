from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Lock

from fastapi import HTTPException, Request

from app.core.config import settings


@dataclass
class _LoginState:
    failures: int = 0
    locked_until: datetime | None = None


_lock = Lock()
_login_states: dict[str, _LoginState] = {}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _client_key(request: Request, email: str) -> str:
    client = request.client.host if request.client else "unknown"
    return f"{client}:{email.lower()}"


def check_login_allowed(request: Request, email: str) -> None:
    key = _client_key(request, email)
    with _lock:
        state = _login_states.get(key)
        if state and state.locked_until and state.locked_until > _utc_now():
            raise HTTPException(
                status_code=429,
                detail="Too many failed login attempts. Try again later.",
            )


def record_login_failure(request: Request, email: str) -> None:
    key = _client_key(request, email)
    with _lock:
        state = _login_states.setdefault(key, _LoginState())
        state.failures += 1
        if state.failures >= settings.login_max_attempts:
            state.locked_until = _utc_now() + timedelta(minutes=settings.login_lockout_minutes)


def clear_login_failures(request: Request, email: str) -> None:
    key = _client_key(request, email)
    with _lock:
        _login_states.pop(key, None)
