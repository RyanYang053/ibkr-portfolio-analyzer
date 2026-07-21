from secrets import token_urlsafe

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.local_runtime import LocalRuntime
from app.middleware.local_session import LocalSessionMiddleware


def _app_with_middleware(token: str) -> TestClient:
    app = FastAPI()

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/portfolio/summary")
    def summary():
        return {"nav": 1}

    runtime = LocalRuntime(
        host="127.0.0.1",
        port=49182,
        session_token=token,
        parent_process_id=1,
    )
    app.add_middleware(LocalSessionMiddleware, runtime=runtime)
    return TestClient(app)


def test_public_health_does_not_require_session():
    token = token_urlsafe(32)
    client = _app_with_middleware(token)
    response = client.get("/health")
    assert response.status_code == 200


def test_options_preflight_does_not_require_session():
    token = token_urlsafe(32)
    client = _app_with_middleware(token)
    response = client.options(
        "/portfolio/summary",
        headers={
            "Origin": "http://tauri.localhost",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-local-session",
        },
    )
    assert response.status_code != 401


def test_protected_route_requires_local_session_header():
    token = token_urlsafe(32)
    client = _app_with_middleware(token)

    denied = client.get("/portfolio/summary")
    assert denied.status_code == 401

    allowed = client.get(
        "/portfolio/summary",
        headers={"X-Local-Session": token},
    )
    assert allowed.status_code == 200
    assert allowed.json()["nav"] == 1
