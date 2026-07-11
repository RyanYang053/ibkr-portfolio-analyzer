from fastapi.testclient import TestClient

from app.main import app
from app.services.broker.ibkr_readonly import (
    allocate_readonly_client_id,
    configure_runtime_ibkr,
    get_runtime_ibkr_config,
)


def test_configure_ibkr_endpoint_accepts_local_gateway_settings_without_credentials():
    client = TestClient(app)

    response = client.post(
        "/broker/configure-readonly",
        json={"host": "127.0.0.1", "port": 4002, "client_id": 10, "account_id": ""},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is True
    assert payload["host"] == "127.0.0.1"
    assert payload["port"] == 4002
    assert payload["trading"] == "disabled"
    assert "password" not in response.text.lower()
    assert "username" not in response.text.lower()


def test_runtime_ibkr_config_is_readonly():
    configure_runtime_ibkr(host="127.0.0.1", port=4002, client_id=10, account_id=None)

    config = get_runtime_ibkr_config()

    assert config["host"] == "127.0.0.1"
    assert config["port"] == 4002
    assert config["client_id"] == 10
    assert config["read_only"] is True


def test_readonly_ibkr_connections_use_unique_client_ids():
    first = allocate_readonly_client_id(10)
    second = allocate_readonly_client_id(10)

    assert first != second
    assert 10 <= first < 1010
    assert 10 <= second < 1010
