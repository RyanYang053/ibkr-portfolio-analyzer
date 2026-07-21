"""Dialect helpers for repository SQL (Postgres JSONB vs SQLite JSON)."""

from __future__ import annotations

from app.core.config import settings


def json_cast(param: str = "payload_json") -> str:
    """Return CAST fragment appropriate for the active persistence backend."""
    backend = (settings.persistence_backend or "").lower()
    if backend in {"sqlite", "json"}:
        return f"CAST(:{param} AS JSON)"
    return f"CAST(:{param} AS jsonb)"


def uses_postgres_sql() -> bool:
    return (settings.persistence_backend or "").lower() == "postgres"
