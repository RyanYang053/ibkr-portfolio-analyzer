from app.db.legacy_bridge import read_json_with_legacy, write_json_state
from app.db.state_store import JsonStateStore, get_state_store


def test_json_state_store_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("app.db.state_store._data_dir", lambda: str(tmp_path))
    store = JsonStateStore()
    store.write_json("test_ns", "alpha", {"value": 1})
    assert store.read_json("test_ns", "alpha") == {"value": 1}


def test_legacy_bridge_migrates_file(tmp_path, monkeypatch):
    monkeypatch.setattr("app.db.state_store._data_dir", lambda: str(tmp_path / "state"))
    legacy = tmp_path / "legacy.json"
    legacy.write_text('[{"date": "2026-01-01"}]', encoding="utf-8")
    payload = read_json_with_legacy("pnl_history", "acct", str(legacy), default=[])
    assert payload == [{"date": "2026-01-01"}]
    assert get_state_store().read_json("pnl_history", "acct") == [{"date": "2026-01-01"}]


def test_write_json_state_persists(tmp_path, monkeypatch):
    monkeypatch.setattr("app.db.state_store._data_dir", lambda: str(tmp_path))
    write_json_state("watchlist", "items", [{"symbol": "AAPL"}])
    assert get_state_store().read_json("watchlist", "items") == [{"symbol": "AAPL"}]
