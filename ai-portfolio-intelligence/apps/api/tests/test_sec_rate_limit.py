from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest


def test_sec_edgar_postgres_gate_serializes_requests(monkeypatch):
    executed: list[str] = []

    class FakeSession:
        def execute(self, statement, params=None):
            executed.append(str(statement))
            return MagicMock()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeBegin:
        def __enter__(self):
            return FakeSession()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("app.core.config.settings.persistence_backend", "postgres")
    monkeypatch.setattr("app.core.config.settings.sec_edgar_requests_per_second", 10.0)
    monkeypatch.setattr("app.core.sec_rate_limit._table_available", lambda: True)
    monkeypatch.setattr("app.db.session.SessionLocal.begin", lambda: FakeBegin())

    from app.core.sec_rate_limit import throttle_sec_edgar_request

    throttle_sec_edgar_request()
    assert any("pg_advisory_xact_lock" in sql for sql in executed)
    assert any("sec_edgar_request_gate" in sql for sql in executed)


def test_sec_edgar_local_fallback_uses_thread_lock(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.persistence_backend", "json")
    monkeypatch.setattr("app.core.sec_rate_limit._table_available", lambda: False)
    monkeypatch.setattr("app.core.config.settings.sec_edgar_requests_per_second", 1000.0)

    from app.core import sec_rate_limit

    sec_rate_limit._LAST_REQUEST_AT = None
    sec_rate_limit.throttle_sec_edgar_request()
    assert sec_rate_limit._LAST_REQUEST_AT is not None
