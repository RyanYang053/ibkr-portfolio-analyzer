from __future__ import annotations

import asyncio

import pytest

from app.worker import _ensure_database_ready, main


def test_worker_refuses_weak_production_configuration(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.environment", "production")
    monkeypatch.setattr("app.core.config.settings.jwt_secret", "dev-only-change-me")

    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        asyncio.run(main())


def test_worker_checks_database_readiness_in_production(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.environment", "production")
    monkeypatch.setattr("app.core.config.settings.jwt_secret", "strong-production-secret-value")
    monkeypatch.setattr("app.core.config.settings.bootstrap_token", "bootstrap-secret")
    monkeypatch.setattr("app.core.config.settings.persistence_backend", "postgres")
    monkeypatch.setattr("app.core.config.settings.scheduler_enabled", False)
    monkeypatch.setattr("app.worker._ensure_database_ready", lambda: (_ for _ in ()).throw(RuntimeError("db down")))

    with pytest.raises(RuntimeError, match="db down"):
        asyncio.run(main())


def test_ensure_database_ready_requires_postgres_connection(monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.health._postgres_ready",
        lambda: (False, "connection refused"),
    )

    with pytest.raises(RuntimeError, match="Postgres is not ready"):
        _ensure_database_ready()
