from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.core.config import settings

router = APIRouter(tags=["health"])


def _safe_detail(code: str) -> str:
    return code


def _postgres_ready() -> tuple[bool, str]:
    if settings.persistence_backend != "postgres":
        return True, "json_backend"
    try:
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
        return True, "connected"
    except Exception:
        return False, "postgres_unavailable"


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
            return False, "migration_head_mismatch"
        return True, "at_head"
    except Exception:
        return False, "alembic_check_failed"


def _governance_tables_ready() -> tuple[bool, str]:
    if settings.persistence_backend != "postgres":
        return True, "not_required"
    try:
        from sqlalchemy import text

        from app.db.session import SessionLocal

        required = ("methodologies", "methodology_versions", "benchmark_definitions")
        with SessionLocal() as session:
            for table in required:
                session.execute(text(f"SELECT 1 FROM {table} LIMIT 1"))
        return True, "present"
    except Exception:
        return False, "governance_tables_unavailable"


def _scheduler_ready() -> tuple[bool, str]:
    if not settings.scheduler_enabled:
        return True, "disabled"
    if settings.persistence_backend != "postgres":
        return True, "not_required"
    try:
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            row = session.execute(
                text(
                    """
                    SELECT heartbeat_at
                    FROM scheduled_jobs
                    WHERE heartbeat_at IS NOT NULL
                    ORDER BY heartbeat_at DESC
                    LIMIT 1
                    """
                )
            ).first()
        if row is None:
            return True, "no_runs_yet"
        updated_at = row[0]
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - updated_at).total_seconds()
        if age_seconds > max(settings.scheduler_lease_minutes * 60 * 4, 3600):
            return False, "scheduler_stale"
        return True, "recent_activity"
    except Exception:
        return False, "scheduler_check_failed"


def _broker_ready() -> tuple[bool, str]:
    if settings.broker_mode == "mock_ibkr_readonly":
        return True, "mock_mode"
    host = settings.ibkr_host
    if host in {"127.0.0.1", "localhost"} and settings.environment == "production":
        return False, "invalid_production_broker_host"
    if settings.environment == "production" and not settings.sec_edgar_user_agent:
        return False, "sec_contact_missing"
    return True, "configured"


@router.get("/health/live")
def health_live() -> dict[str, str]:
    return {"status": "alive", "mode": settings.broker_mode}


@router.get("/health/ready")
def health_ready() -> dict[str, object]:
    checks: dict[str, object] = {}
    failures: list[str] = []

    postgres_ok, postgres_detail = _postgres_ready()
    checks["postgres"] = {"ok": postgres_ok, "detail": _safe_detail(postgres_detail)}
    if not postgres_ok:
        failures.append("postgres")

    alembic_ok, alembic_detail = _alembic_ready()
    checks["alembic"] = {"ok": alembic_ok, "detail": _safe_detail(alembic_detail)}
    if settings.persistence_backend == "postgres" and not alembic_ok:
        failures.append("alembic")

    governance_ok, governance_detail = _governance_tables_ready()
    checks["governance_tables"] = {"ok": governance_ok, "detail": _safe_detail(governance_detail)}
    if settings.environment == "production" and settings.persistence_backend == "postgres" and not governance_ok:
        failures.append("governance_tables")

    scheduler_ok, scheduler_detail = _scheduler_ready()
    checks["scheduler"] = {"ok": scheduler_ok, "detail": _safe_detail(scheduler_detail)}
    if settings.environment == "production" and settings.scheduler_enabled and not scheduler_ok:
        failures.append("scheduler")

    broker_ok, broker_detail = _broker_ready()
    checks["broker_config"] = {"ok": broker_ok, "detail": _safe_detail(broker_detail)}
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
    governance_ok, governance_detail = _governance_tables_ready()
    scheduler_ok, scheduler_detail = _scheduler_ready()
    return {
        "postgres": {"ok": postgres_ok, "detail": _safe_detail(postgres_detail)},
        "alembic": {"ok": alembic_ok, "detail": _safe_detail(alembic_detail)},
        "governance_tables": {"ok": governance_ok, "detail": _safe_detail(governance_detail)},
        "scheduler": {"ok": scheduler_ok, "detail": _safe_detail(scheduler_detail)},
        "broker_config": {"ok": broker_ok, "detail": _safe_detail(broker_detail)},
        "flex_configured": bool(settings.ibkr_flex_token and settings.ibkr_flex_activity_query_id),
        "scheduler_enabled": settings.scheduler_enabled,
        "environment": settings.environment,
    }
