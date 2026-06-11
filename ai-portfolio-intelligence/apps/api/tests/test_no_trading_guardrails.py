from fastapi.testclient import TestClient

from app.main import app
from app.services.broker.base import BrokerAdapter


FORBIDDEN_ROUTES = {
    "/orders/submit",
    "/orders/place",
    "/orders/execute",
    "/trades/execute",
    "/rebalance/execute",
    "/portfolio/rebalance",
    "/options/execute",
    "/broker/order",
    "/broker/trade",
}

FORBIDDEN_METHOD_NAMES = {
    "place_order",
    "modify_order",
    "cancel_order",
    "execute_trade",
    "rebalance",
    "submit_order",
}


def test_broker_adapter_exposes_only_readonly_methods():
    adapter_methods = {
        name
        for name in dir(BrokerAdapter)
        if not name.startswith("_") and callable(getattr(BrokerAdapter, name))
    }

    assert FORBIDDEN_METHOD_NAMES.isdisjoint(adapter_methods)
    assert {
        "get_accounts",
        "get_account_summary",
        "get_positions",
        "get_transactions",
        "get_open_orders_readonly",
        "get_latest_price",
        "health_check",
    }.issubset(adapter_methods)


def test_fastapi_app_does_not_register_forbidden_trading_routes():
    registered_routes = {route.path for route in app.routes}

    assert FORBIDDEN_ROUTES.isdisjoint(registered_routes)


def test_forbidden_trading_route_returns_not_found():
    client = TestClient(app)

    response = client.post("/orders/submit", json={"symbol": "MSFT"})

    assert response.status_code == 404
