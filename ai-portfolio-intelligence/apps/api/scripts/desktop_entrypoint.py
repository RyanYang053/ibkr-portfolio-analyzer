"""Packaged desktop FastAPI entrypoint (PyInstaller sidecar)."""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from pathlib import Path

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


def configure_logging(data_dir: Path) -> None:
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "sidecar.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
        force=True,
    )
    logging.getLogger(__name__).info("Sidecar logging to %s", log_path)


def start_parent_watchdog() -> None:
    raw = os.getenv("LOCAL_PARENT_PID", "").strip()
    if not raw:
        return
    try:
        parent_pid = int(raw)
    except ValueError:
        return

    def _watch() -> None:
        while True:
            time.sleep(2.0)
            try:
                os.kill(parent_pid, 0)
            except OSError:
                logging.getLogger(__name__).warning(
                    "Parent process %s exited; shutting down sidecar",
                    parent_pid,
                )
                os._exit(0)

    threading.Thread(target=_watch, name="parent-watchdog", daemon=True).start()


def main() -> None:
    host = required_environment("LOCAL_API_HOST")
    port = int(required_environment("LOCAL_API_PORT"))
    # Token must be present so LocalSessionMiddleware can load; value is not logged.
    required_environment("LOCAL_SESSION_TOKEN")
    assert_loopback_bind(host)

    data_dir = Path(os.getenv("PORTFOLIO_DATA_DIR", ".")).expanduser()
    data_dir.mkdir(parents=True, exist_ok=True)
    configure_logging(data_dir)
    start_parent_watchdog()

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
