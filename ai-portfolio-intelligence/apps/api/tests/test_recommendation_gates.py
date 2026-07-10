import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_broker_adapter
from app.main import app
from app.services.broker.mock_ibkr import MockIBKRAdapter


@pytest.fixture
def mock_client(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.broker_mode", "mock_ibkr_readonly")
    app.dependency_overrides[get_broker_adapter] = lambda: MockIBKRAdapter()
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_recommendations_include_con_id_and_validation_fields(mock_client):
    response = mock_client.get("/recommendations?account_id=MOCK-001")
    assert response.status_code == 200
    payload = response.json()
    assert "snapshot_validation" in payload
    assert "valuation_disclosure" in payload
    recommendations = payload["recommendations"]
    assert recommendations
    assert recommendations[0]["con_id"] is not None


def test_single_recommendation_by_con_id(mock_client):
    response = mock_client.get("/recommendations/MSFT?account_id=MOCK-001&con_id=272093")
    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "MSFT"
    assert payload["con_id"] == 272093
    assert "snapshot_validation" in payload
