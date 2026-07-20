from __future__ import annotations

from app.db.state_migration import MIGRATION_MARKER, migrate_legacy_state_layout
from app.db.state_store import JsonStateStore, StateStoreError


def test_legacy_readable_paths_migrate_to_hashed_layout(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTFOLIO_DATA_DIR", str(tmp_path))
    state = tmp_path / "state"
    thesis_dir = state / "holding_theses"
    thesis_dir.mkdir(parents=True)
    (thesis_dir / "U0001:AAPL.json").write_text(
        '{"summary": "Quality compounder"}',
        encoding="utf-8",
    )
    watch_dir = state / "watchlist"
    watch_dir.mkdir(parents=True)
    (watch_dir / "local-owner.json").write_text(
        '{"symbols": ["AAPL"]}',
        encoding="utf-8",
    )
    broker_dir = state / "broker"
    broker_dir.mkdir(parents=True)
    (broker_dir / "runtime_config.json").write_text(
        '{"mode": "mock_ibkr_readonly", "host": "127.0.0.1"}',
        encoding="utf-8",
    )

    result = migrate_legacy_state_layout(state)
    assert result["migrated"] is True
    assert result["records"] == 3
    assert (state / MIGRATION_MARKER).exists()

    store = JsonStateStore()
    assert store.read_json("holding_theses", "U0001:AAPL") == {
        "summary": "Quality compounder"
    }
    assert store.read_json("watchlist", "local-owner") == {"symbols": ["AAPL"]}
    assert store.read_json("broker", "runtime_config")["mode"] == "mock_ibkr_readonly"

    # Legacy originals are renamed, not left as active paths.
    assert not (thesis_dir / "U0001:AAPL.json").exists()
    assert (thesis_dir / "U0001:AAPL.migrated.json").exists()

    second = migrate_legacy_state_layout(state)
    assert second["already_complete"] is True
    assert second["records"] == 0


def test_corrupt_legacy_record_blocks_marker(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTFOLIO_DATA_DIR", str(tmp_path))
    state = tmp_path / "state"
    bad = state / "watchlist"
    bad.mkdir(parents=True)
    (bad / "local-owner.json").write_text("{not-json", encoding="utf-8")

    try:
        migrate_legacy_state_layout(state)
        raised = False
    except StateStoreError:
        raised = True
    assert raised
    assert not (state / MIGRATION_MARKER).exists()
