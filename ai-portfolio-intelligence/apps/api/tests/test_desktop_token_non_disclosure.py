from secrets import token_urlsafe

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.local_runtime import LocalRuntime
from app.middleware.local_session import PUBLIC_PATHS, LocalSessionMiddleware


def test_public_paths_do_not_include_root_or_ui():
    assert "/" not in PUBLIC_PATHS
    assert "/ui/app.js" not in PUBLIC_PATHS
    assert "/health/ready" not in PUBLIC_PATHS
    assert "/health" in PUBLIC_PATHS
    assert "/health/live" in PUBLIC_PATHS
    assert "/version" in PUBLIC_PATHS


def test_public_endpoints_do_not_expose_session_token():
    token = token_urlsafe(32)
    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "healthy"}

    @app.get("/")
    def root():
        return {"name": "Portfolio Analyzer"}

    runtime = LocalRuntime(
        host="127.0.0.1",
        port=49182,
        session_token=token,
        parent_process_id=1,
    )
    app.add_middleware(LocalSessionMiddleware, runtime=runtime)
    client = TestClient(app)

    health_response = client.get("/health")
    assert health_response.status_code == 200
    assert token not in health_response.text
    assert "__DESKTOP_RUNTIME__" not in health_response.text

    root_response = client.get("/")
    assert root_response.status_code == 401
    assert token not in root_response.text
    assert "__DESKTOP_RUNTIME__" not in root_response.text


def test_desktop_ui_module_removed():
    import importlib.util

    spec = importlib.util.find_spec("app.api.routes.desktop_ui")
    assert spec is None
