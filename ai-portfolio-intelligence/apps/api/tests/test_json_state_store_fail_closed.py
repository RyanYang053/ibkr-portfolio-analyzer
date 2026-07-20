
import pytest

from app.db.state_store import JsonStateStore, StateCorruptionError


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTFOLIO_DATA_DIR", str(tmp_path))
    return JsonStateStore()


def test_missing_file_returns_default(store):
    assert store.read_json("portfolio", "summary", default={"empty": True}) == {"empty": True}


def test_corrupt_json_is_quarantined(store, tmp_path):
    path = store._path("portfolio", "summary")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(StateCorruptionError, match="quarantined"):
        store.read_json("portfolio", "summary")

    quarantined = list(path.parent.glob("*.corrupt-*.json"))
    assert len(quarantined) == 1
    assert not path.exists()


def test_write_and_read_roundtrip(store):
    store.write_json("portfolio", "summary", {"nav": 100})
    assert store.read_json("portfolio", "summary") == {"nav": 100}


def test_path_uses_hashed_components(store):
    path = store._path("../escape", "../../key")
    assert "escape" not in str(path)
    assert ".." not in path.parts
    assert path.suffix == ".json"


def test_delete_removes_record(store):
    store.write_json("portfolio", "summary", {"nav": 1})
    store.delete("portfolio", "summary")
    assert store.read_json("portfolio", "summary", default=None) is None


def test_explicit_root_ignores_env(tmp_path, monkeypatch):
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setenv("PORTFOLIO_DATA_DIR", str(other))
    target = tmp_path / "target-state"
    target.mkdir()
    store = JsonStateStore(root=target)
    store.write_json("watchlist", "local-owner", {"symbols": ["AAPL"]})
    written = list(target.rglob("*.json"))
    assert written
    assert not list(other.rglob("*.json"))
