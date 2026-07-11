from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings


@dataclass
class _LoginState:
    failures: int = 0
    locked_until: datetime | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _client_ip(request: Request) -> str:
    direct = request.client.host if request.client else "unknown"
    if direct in settings.trusted_proxies:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return direct


def _rate_limit_keys(request: Request, email: str) -> list[str]:
    ip = _client_ip(request)
    normalized_email = email.lower()
    return [
        f"account:{normalized_email}",
        f"ip:{ip}",
        f"ip_email:{ip}:{normalized_email}",
    ]


def _table_available() -> bool:
    if settings.persistence_backend != "postgres":
        return False
    try:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(text("SELECT 1 FROM login_rate_limits LIMIT 1"))
        return True
    except SQLAlchemyError:
        return False


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


def _is_locked(locked_until: datetime | None, now: datetime) -> bool:
    return locked_until is not None and locked_until > now


def _postgres_check_allowed(keys: list[str]) -> None:
    from app.db.session import SessionLocal

    now = _utc_now()
    with SessionLocal() as session:
        rows = session.execute(
            text(
                """
                SELECT client_key, locked_until
                FROM login_rate_limits
                WHERE client_key = ANY(:keys)
                """
            ),
            {"keys": keys},
        ).mappings().all()
        for row in rows:
            locked_until = row.get("locked_until")
            if locked_until is not None and locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=timezone.utc)
            if _is_locked(locked_until, now):
                raise HTTPException(
                    status_code=429,
                    detail="Too many failed login attempts. Try again later.",
                )


def _postgres_record_failure(keys: list[str]) -> None:
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        for key in keys:
            session.execute(
                text(
                    """
                    INSERT INTO login_rate_limits (
                        client_key, failures, locked_until, updated_at
                    )
                    VALUES (:key, 1, NULL, NOW())
                    ON CONFLICT (client_key)
                    DO UPDATE SET
                        failures = CASE
                            WHEN login_rate_limits.locked_until IS NOT NULL
                             AND login_rate_limits.locked_until <= NOW()
                            THEN 1
                            ELSE login_rate_limits.failures + 1
                        END,
                        locked_until = CASE
                            WHEN (
                                CASE
                                    WHEN login_rate_limits.locked_until IS NOT NULL
                                     AND login_rate_limits.locked_until <= NOW()
                                    THEN 1
                                    ELSE login_rate_limits.failures + 1
                                END
                            ) >= :max_attempts
                            THEN NOW() + (:lockout_minutes || ' minutes')::interval
                            ELSE login_rate_limits.locked_until
                        END,
                        updated_at = NOW()
                    """
                ),
                {
                    "key": key,
                    "max_attempts": settings.login_max_attempts,
                    "lockout_minutes": settings.login_lockout_minutes,
                },
            )
        session.commit()


def _postgres_clear_failures(keys: list[str]) -> None:
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        session.execute(
            text("DELETE FROM login_rate_limits WHERE client_key = ANY(:keys)"),
            {"keys": keys},
        )
        session.commit()


def _json_check_allowed(keys: list[str]) -> None:
    now = _utc_now()
    for key in keys:
        state = _load_persistent_state(key)
        if state and _is_locked(state.locked_until, now):
            raise HTTPException(
                status_code=429,
                detail="Too many failed login attempts. Try again later.",
            )


def _json_record_failure(keys: list[str]) -> None:
    now = _utc_now()
    for key in keys:
        state = _load_persistent_state(key) or _LoginState()
        if state.locked_until and state.locked_until <= now:
            state.failures = 0
            state.locked_until = None
        state.failures += 1
        if state.failures >= settings.login_max_attempts:
            state.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
        _save_persistent_state(key, state)


def _json_clear_failures(keys: list[str]) -> None:
    for key in keys:
        _delete_persistent_state(key)


def check_login_allowed(request: Request, email: str) -> None:
    keys = _rate_limit_keys(request, email)
    if _table_available():
        _postgres_check_allowed(keys)
        return
    _json_check_allowed(keys)


def record_login_failure(request: Request, email: str) -> None:
    keys = _rate_limit_keys(request, email)
    if _table_available():
        _postgres_record_failure(keys)
        return
    _json_record_failure(keys)


def clear_login_failures(request: Request, email: str) -> None:
    keys = _rate_limit_keys(request, email)
    if _table_available():
        _postgres_clear_failures(keys)
        return
    _json_clear_failures(keys)
