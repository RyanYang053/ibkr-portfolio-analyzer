"""Database health checks for desktop SQLite / postgres."""

from __future__ import annotations

from typing import Any

from app.core.config import settings


def database_health() -> dict[str, Any]:
    backend = settings.persistence_backend
    result: dict[str, Any] = {
        "persistence_backend": backend,
        "database_url_scheme": str(settings.database_url).split(":", 1)[0],
        "ok": True,
        "checks": [],
    }
    if backend == "json":
        result["checks"].append({"id": "json_state", "status": "available"})
        return result

    try:
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
            if str(settings.database_url).startswith("sqlite"):
                row = session.execute(text("PRAGMA integrity_check")).fetchone()
                integrity = row[0] if row else "unknown"
                result["checks"].append(
                    {
                        "id": "sqlite_integrity",
                        "status": "available" if integrity == "ok" else "failed",
                        "detail": integrity,
                    }
                )
                if integrity != "ok":
                    result["ok"] = False
            else:
                result["checks"].append({"id": "postgres_ping", "status": "available"})
    except Exception as exc:
        result["ok"] = False
        result["checks"].append({"id": "connection", "status": "failed", "detail": str(exc)})
    return result
