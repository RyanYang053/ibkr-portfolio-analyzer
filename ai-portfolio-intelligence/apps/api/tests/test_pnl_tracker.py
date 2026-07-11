import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_broker_adapter
from app.api.routes import ai as ai_routes
from app.main import app
from app.services.broker.mock_ibkr import MockIBKRAdapter
from app.services.portfolio import pnl_tracker


@pytest.fixture(autouse=True)
def isolate_persisted_test_data(tmp_path, monkeypatch):
    monkeypatch.setattr(pnl_tracker, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(pnl_tracker, "HISTORY_FILE", str(tmp_path / "pnl_history.json"))
    monkeypatch.setattr(ai_routes, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(ai_routes, "SETTINGS_FILE", str(tmp_path / "schedule_settings.json"))
    monkeypatch.setattr(ai_routes, "RUNS_FILE", str(tmp_path / "schedule_runs.json"))


def test_demo_pnl_history_is_explicitly_marked_mock(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.broker_mode", "mock_ibkr_readonly")
    history = pnl_tracker.get_pnl_history()

    assert len(history) >= 10
    assert all(entry.is_mock for entry in history)
    assert all(entry.net_liquidation > 0 for entry in history)


def test_pnl_snapshot_calculation():
    adapter = MockIBKRAdapter()
    summary = adapter.get_account_summary("MOCK-001")
    positions = adapter.get_positions("MOCK-001")

    snapshot = pnl_tracker.record_pnl_snapshot(summary, positions)

    assert snapshot.net_liquidation == round(summary.net_liquidation, 2)
    assert snapshot.cash == round(summary.cash, 2)
    assert snapshot.positions


def test_pnl_endpoints_use_broker_override():
    app.dependency_overrides[get_broker_adapter] = lambda: MockIBKRAdapter()
    client = TestClient(app)
    try:
        recorded = client.post("/portfolio/pnl-history/record?account_id=MOCK-001")
        assert recorded.status_code == 200
        assert recorded.json()["net_liquidation"] > 0
        response = client.get("/portfolio/pnl-history?account_id=MOCK-001")
        assert response.status_code == 200
        assert response.json()
    finally:
        app.dependency_overrides.clear()


def test_ai_scheduling_endpoints_use_isolated_storage():
    client = TestClient(app)
    response = client.get("/ai/schedule")
    assert response.status_code == 200

    payload = {
        "enabled": True,
        "morning_time": "08:45",
        "midday_time": "12:15",
        "night_time": "19:30",
    }
    updated = client.put("/ai/schedule", json=payload)
    assert updated.status_code == 200
    assert updated.json()["settings"] == payload

    app.dependency_overrides[get_broker_adapter] = lambda: MockIBKRAdapter()
    try:
        analyzed = client.post("/ai/scheduled-analyze?account_id=MOCK-001", json={"period": "midday"})
        assert analyzed.status_code == 200
        assert analyzed.json()["period"] == "midday"
    finally:
        app.dependency_overrides.clear()
