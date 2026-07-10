from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.broker.ibkr_readonly import configure_runtime_ibkr


def test_default_broker_mode_is_not_mock_data():
    assert settings.broker_mode == "ibkr_readonly"


def test_broker_status_reports_live_readonly_placeholder_not_mock(monkeypatch):
    monkeypatch.setattr(settings, "broker_mode", "ibkr_readonly")
    client = TestClient(app)

    response = client.get("/broker/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "ibkr_readonly"
    assert payload["trading"] == "disabled"


def test_portfolio_summary_returns_not_configured_when_mock_disabled(monkeypatch):
    monkeypatch.setattr(settings, "broker_mode", "ibkr_readonly")
    configure_runtime_ibkr(host="127.0.0.1", port=65534, client_id=9999, account_id=None)
    client = TestClient(app)

    response = client.get("/portfolio/summary")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "BROKER_NOT_CONFIGURED"
