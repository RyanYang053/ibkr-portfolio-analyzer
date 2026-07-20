"""Network binding policy for the desktop-local product."""

from __future__ import annotations

import sys

from app.core.deployment_mode import DeploymentMode


LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def assert_loopback_bind(host: str) -> None:
    if host not in {"127.0.0.1", "::1"}:
        raise RuntimeError("Packaged / desktop backend may bind only to loopback")


def assert_deployment_network_policy(
    *,
    deployment_mode: DeploymentMode | str,
    bind_host: str,
    database_url: str,
    persistence_backend: str = "json",
) -> None:
    mode = DeploymentMode(deployment_mode)
    if mode != DeploymentMode.DESKTOP_LOCAL:
        return

    assert_loopback_bind(bind_host)
    if persistence_backend != "json":
        raise RuntimeError("DESKTOP_LOCAL persistence must be json")


def is_loopback_client(host: str | None) -> bool:
    if host in {"127.0.0.1", "::1"}:
        return True
    # Starlette/FastAPI TestClient presents as "testclient".
    if host == "testclient" and "pytest" in sys.modules:
        return True
    return False
