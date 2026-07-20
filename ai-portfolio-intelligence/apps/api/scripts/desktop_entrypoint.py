"""Packaged desktop FastAPI entrypoint (PyInstaller sidecar)."""

from __future__ import annotations

import os
import sys

# Ensure the packaged app package is importable when frozen.
if getattr(sys, "frozen", False):
    bundle_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    if bundle_dir not in sys.path:
        sys.path.insert(0, bundle_dir)

import uvicorn

from app.core.network_policy import assert_loopback_bind


def required_environment(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required setting: {name}")
    return value


def main() -> None:
    host = required_environment("LOCAL_API_HOST")
    port = int(required_environment("LOCAL_API_PORT"))
    # Token must be present so LocalSessionMiddleware can load; value is not logged.
    required_environment("LOCAL_SESSION_TOKEN")
    assert_loopback_bind(host)

    # Import after env validation so settings pick up desktop env vars.
    from app.main import app

    uvicorn.run(
        app,
        host=host,
        port=port,
        access_log=False,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
