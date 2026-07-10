from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.config import settings

router = APIRouter(tags=["health"])


def _postgres_ready() -> tuple[bool, str]:
    if settings.persistence_backend != "postgres":
        return True, "json_backend"
    try:
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
        return True, "connected"
    except Exception as exc:
        return False, str(exc)


def _alembic_ready() -> tuple[bool, str]:
    if settings.persistence_backend != "postgres":
        return True, "not_required"
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from sqlalchemy import text

        from app.db.session import SessionLocal

        config = Config("alembic.ini")
        script = ScriptDirectory.from_config(config)
        head = script.get_current_head()
        with SessionLocal() as session:
            row = session.execute(text("SELECT version_num FROM alembic_version")).first()
        current = row[0] if row else None
        if current != head:
            return False, f"current={current} head={head}"
        return True, current or head
    except Exception as exc:
        return False, str(exc)


def _broker_ready() -> tuple[bool, str]:
    if settings.broker_mode == "mock_ibkr_readonly":
        return True, "mock_mode"
    host = settings.ibkr_host
    if host in {"127.0.0.1", "localhost"} and settings.environment == "production":
        return False, "localhost_ibkr_host_in_production"
    return True, host


@router.get("/health/live")
def health_live() -> dict[str, str]:
    return {"status": "alive", "mode": settings.broker_mode}


@router.get("/health/ready")
def health_ready() -> dict[str, object]:
    checks: dict[str, object] = {}
    failures: list[str] = []

    postgres_ok, postgres_detail = _postgres_ready()
    checks["postgres"] = {"ok": postgres_ok, "detail": postgres_detail}
    if not postgres_ok:
        failures.append("postgres")

    alembic_ok, alembic_detail = _alembic_ready()
    checks["alembic"] = {"ok": alembic_ok, "detail": alembic_detail}
    if settings.persistence_backend == "postgres" and not alembic_ok:
        failures.append("alembic")

    broker_ok, broker_detail = _broker_ready()
    checks["broker_config"] = {"ok": broker_ok, "detail": broker_detail}
    if settings.environment == "production" and not broker_ok:
        failures.append("broker_config")

    if settings.environment == "production" and not settings.jwt_secret:
        checks["jwt_secret"] = {"ok": False, "detail": "missing"}
        failures.append("jwt_secret")
    else:
        checks["jwt_secret"] = {"ok": True, "detail": "configured"}

    if failures:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "checks": checks,
                "failures": failures,
            },
        )
    return {"status": "ready", "checks": checks}


@router.get("/health/dependencies")
def health_dependencies() -> dict[str, object]:
    postgres_ok, postgres_detail = _postgres_ready()
    alembic_ok, alembic_detail = _alembic_ready()
    broker_ok, broker_detail = _broker_ready()
    return {
        "postgres": {"ok": postgres_ok, "detail": postgres_detail},
        "alembic": {"ok": alembic_ok, "detail": alembic_detail},
        "broker_config": {"ok": broker_ok, "detail": broker_detail},
        "flex_configured": bool(settings.ibkr_flex_token and settings.ibkr_flex_activity_query_id),
        "scheduler_enabled": settings.scheduler_enabled,
        "environment": settings.environment,
    }
