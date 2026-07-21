"""Cold SQLite Alembic upgrade from empty database to head."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text


def test_alembic_upgrade_head_on_empty_sqlite(tmp_path, monkeypatch) -> None:
    """Upgrade empty SQLite through the full migration chain to the current head."""
    # Remaining blockers (if any) should be fixed in migrations, not skipped here.
    db_path = Path(tmp_path) / "cold_upgrade.db"
    database_url = f"sqlite+pysqlite:///{db_path}"

    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("PERSISTENCE_BACKEND", "sqlite")

    from app.core.config import settings

    monkeypatch.setattr(settings, "database_url", database_url)
    monkeypatch.setattr(settings, "persistence_backend", "sqlite")

    api_root = Path(__file__).resolve().parents[2]
    alembic_ini = api_root / "alembic.ini"
    cfg = Config(str(alembic_ini))
    cfg.set_main_option("sqlalchemy.url", database_url)
    cfg.set_main_option("script_location", str(api_root / "app" / "db" / "migrations"))

    command.upgrade(cfg, "head")

    expected_head = ScriptDirectory.from_config(cfg).get_current_head()

    engine = create_engine(database_url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert version is not None
        # Cold upgrade must land on the current migration head, whatever it is.
        assert version == expected_head

        tables = set(inspect(conn).get_table_names())
        assert (
            "decision_packets" in tables
            or "evidence_records" in tables
            or "financial_plans" in tables
        )
