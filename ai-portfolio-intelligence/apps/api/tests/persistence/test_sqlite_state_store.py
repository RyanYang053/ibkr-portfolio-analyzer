"""SQLite state store round-trip."""

from __future__ import annotations

from pathlib import Path


def test_sqlite_state_store_roundtrip(tmp_path, monkeypatch) -> None:
    db_path = Path(tmp_path) / "test.db"
    monkeypatch.setenv("PORTFOLIO_DATA_DIR", str(tmp_path))
    from app.core.config import settings

    monkeypatch.setattr(settings, "persistence_backend", "sqlite")
    monkeypatch.setattr(settings, "database_url", f"sqlite+pysqlite:///{db_path}")

    # Rebuild engine binding for the monkeypatched URL.
    from sqlalchemy.orm import sessionmaker
    import app.db.session as session_mod

    session_mod.engine = session_mod._build_engine()
    session_mod.SessionLocal = sessionmaker(
        bind=session_mod.engine, autocommit=False, autoflush=False
    )

    from app.db import state_store as state_store_mod

    state_store_mod._SQLITE_TABLE_READY = False
    store = state_store_mod.SqlStateStore()
    store.write_json("decision_packets", "dec_1", {"decision_id": "dec_1", "outcome": "monitor"})
    row = store.read_json("decision_packets", "dec_1")
    assert row["outcome"] == "monitor"
    assert "dec_1" in store.list_keys("decision_packets")
    store.delete("decision_packets", "dec_1")
    assert store.read_json("decision_packets", "dec_1", default=None) is None
