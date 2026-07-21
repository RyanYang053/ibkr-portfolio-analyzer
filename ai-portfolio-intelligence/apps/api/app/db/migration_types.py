"""Portable SQLAlchemy column helpers for SQLite + PostgreSQL."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import FunctionElement


def json_document_type():
    """JSON that uses JSONB on PostgreSQL and JSON elsewhere (including SQLite)."""
    return sa.JSON().with_variant(
        postgresql.JSONB(astext_type=sa.Text()),
        "postgresql",
    )


def uuid_column_type():
    """UUID on PostgreSQL; CHAR(36) elsewhere for SQLite portability."""
    return sa.String(36).with_variant(postgresql.UUID(as_uuid=True), "postgresql")


def inet_column_type():
    """INET on PostgreSQL; String elsewhere."""
    return sa.String(45).with_variant(postgresql.INET(), "postgresql")


class _UuidServerDefault(FunctionElement):
    """Dialect-compiled UUID default expression for CREATE TABLE server_default."""

    type = sa.String()
    inherit_cache = True
    name = "portable_uuid_server_default"


@compiles(_UuidServerDefault, "postgresql")
def _compile_uuid_server_default_pg(element, compiler, **kw):
    return "gen_random_uuid()"


@compiles(_UuidServerDefault, "sqlite")
def _compile_uuid_server_default_sqlite(element, compiler, **kw):
    return (
        "(lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || "
        "substr(lower(hex(randomblob(2))),2) || '-' || "
        "substr('89ab', abs(random()) % 4 + 1, 1) || substr(lower(hex(randomblob(2))),2) || '-' || "
        "lower(hex(randomblob(6))))"
    )


@compiles(_UuidServerDefault)
def _compile_uuid_server_default_default(element, compiler, **kw):
    return "gen_random_uuid()"


def uuid_server_default():
    """UUID default: gen_random_uuid on Postgres; SQLite hex blob UUID text."""
    return _UuidServerDefault()


def json_server_default_empty_object():
    """Empty JSON object default portable across dialects."""
    return sa.text("'{}'")


def json_server_default_empty_array():
    """Empty JSON array default portable across dialects."""
    return sa.text("'[]'")


def timestamp_now_default():
    """CURRENT_TIMESTAMP on all dialects (avoid PG-only now())."""
    return sa.text("CURRENT_TIMESTAMP")


def is_postgresql_bind(bind) -> bool:
    return getattr(getattr(bind, "dialect", None), "name", "") == "postgresql"


def json_bind_cast_sql(param_name: str = "payload_json") -> str:
    """SQL fragment for binding JSON params: JSONB on Postgres, JSON elsewhere."""
    # Callers still need dialect branching for full portability; this is the PG form.
    return f"CAST(:{param_name} AS jsonb)"
