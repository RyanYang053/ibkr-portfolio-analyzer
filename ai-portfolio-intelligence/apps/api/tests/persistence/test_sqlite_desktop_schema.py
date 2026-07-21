"""Desktop SQLite Decision OS schema bootstrap without full Alembic history."""

from __future__ import annotations

from pathlib import Path


def test_ensure_decision_os_sqlite_tables(tmp_path, monkeypatch) -> None:
    db_path = Path(tmp_path) / "desk.db"
    monkeypatch.setenv("PORTFOLIO_DATA_DIR", str(tmp_path))
    from app.core.config import settings

    monkeypatch.setattr(settings, "persistence_backend", "sqlite")
    monkeypatch.setattr(settings, "database_url", f"sqlite+pysqlite:///{db_path}")

    from sqlalchemy.orm import sessionmaker

    import app.db.session as session_mod

    session_mod.engine = session_mod._build_engine()
    session_mod.SessionLocal = sessionmaker(
        bind=session_mod.engine, autocommit=False, autoflush=False
    )

    from app.db import state_store as state_store_mod
    from app.db.sqlite_desktop_schema import ensure_decision_os_sqlite_tables

    state_store_mod._SQLITE_TABLE_READY = False
    result = ensure_decision_os_sqlite_tables()
    assert result["ok"] is True
    assert "decision_calibration_observations" in result["tables"]
    assert "decision_packets" in result["tables"]
    assert "evidence_records" in result["tables"]
    assert "personal_methodology_approvals" in result["tables"]
    assert "tax_reconciliation_runs" in result["tables"]
    assert result["schema_pin"] == "0036"
