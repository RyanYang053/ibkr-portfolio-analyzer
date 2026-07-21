"""Dialect helpers for repository SQL (Postgres JSONB vs SQLite JSON)."""

from __future__ import annotations

from app.core.config import settings


def json_cast(param: str = "payload_json") -> str:
    """Return a JSON-binding fragment appropriate for the active persistence backend.

    SQLite has no JSON storage class — ``CAST(x AS JSON)`` gets NUMERIC affinity and
    silently stores 0. Use the ``json()`` function instead, which validates the text
    and stores readable JSON. Postgres uses a jsonb cast.
    """
    backend = (settings.persistence_backend or "").lower()
    if backend in {"sqlite", "json"}:
        return f"json(:{param})"
    return f"CAST(:{param} AS jsonb)"


def uses_postgres_sql() -> bool:
    return (settings.persistence_backend or "").lower() == "postgres"
