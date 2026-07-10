from __future__ import annotations

from fastapi import HTTPException

from app.core.config import settings


def require_postgres_persistence(operation: str, *, table_available: bool) -> None:
    if settings.persistence_backend != "postgres":
        return
    if table_available:
        return
    raise HTTPException(
        status_code=503,
        detail={
            "code": "PERSISTENCE_UNAVAILABLE",
            "message": f"Postgres persistence is required but unavailable for {operation}.",
        },
    )


def require_postgres_read(operation: str, *, table_available: bool) -> None:
    """Fail closed when Postgres is configured but the backing table is unavailable."""
    require_postgres_persistence(operation, table_available=table_available)
