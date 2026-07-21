"""Unit of work for multi-table decision packet persistence."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from app.core.config import settings


@contextmanager
def unit_of_work() -> Iterator[object]:
    """Yield a DB session when using postgres/sqlite; otherwise a no-op context."""
    if settings.persistence_backend not in {"postgres", "sqlite"}:
        yield None
        return

    from app.db.session import SessionLocal

    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
