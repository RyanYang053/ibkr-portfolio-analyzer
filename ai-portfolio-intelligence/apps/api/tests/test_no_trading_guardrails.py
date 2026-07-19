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


def _collect_registered_paths(routes) -> set[str]:
    """Collect path strings from FastAPI/Starlette routes, including nested routers.

    FastAPI 0.139+ / Starlette 1.3 may expose ``_IncludedRouter`` entries in
    ``app.routes`` that do not have a ``.path`` attribute.
    """
    paths: set[str] = set()
    for route in routes:
        path = getattr(route, "path", None)
        if isinstance(path, str):
            paths.add(path)
        nested = getattr(route, "routes", None)
        if nested is not None:
            paths |= _collect_registered_paths(nested)
        original = getattr(route, "original_router", None)
        if original is not None:
            paths |= _collect_registered_paths(getattr(original, "routes", []) or [])
    return paths


def test_fastapi_app_does_not_register_forbidden_trading_routes():
    registered_routes = _collect_registered_paths(app.routes)
    # OpenAPI paths cover include_in_schema routes as a second honesty check.
    registered_routes |= set(app.openapi().get("paths", {}))

    assert FORBIDDEN_ROUTES.isdisjoint(registered_routes)


def test_forbidden_trading_route_returns_not_found():
    client = TestClient(app)

    response = client.post("/orders/submit", json={"symbol": "MSFT"})

    assert response.status_code == 404
