#!/usr/bin/env python3
"""Personal local launcher: no Docker, no login, opens the local UI in your browser."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path
from secrets import token_urlsafe


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"


def python_executable() -> str:
    if VENV_PYTHON.exists():
        return str(VENV_PYTHON)
    return sys.executable


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def default_data_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "PortfolioAnalyzer"
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "PortfolioAnalyzer"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "portfolio-analyzer"


def wait_healthy(url: str, timeout: float = 45.0) -> None:
    started = time.time()
    while time.time() - started < timeout:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.25)
    raise SystemExit(f"API did not become healthy at {url}")


def main() -> int:
    data_dir = Path(os.environ.get("PORTFOLIO_DATA_DIR") or default_data_dir())
    data_dir.mkdir(parents=True, exist_ok=True)
    host = "127.0.0.1"
    port = int(os.environ.get("LOCAL_API_PORT") or free_port())
    token = token_urlsafe(32)

    env = os.environ.copy()
    env.update(
        {
            "DEPLOYMENT_MODE": "desktop_local",
            "ENVIRONMENT": "desktop",
            "PERSISTENCE_BACKEND": "json",
            "PORTFOLIO_DATA_DIR": str(data_dir),
            "DATABASE_URL": f"sqlite+pysqlite:///{data_dir / 'portfolio.db'}",
            "LOCAL_API_HOST": host,
            "LOCAL_API_PORT": str(port),
            "LOCAL_SESSION_TOKEN": token,
            "DISABLE_AUTH_ENFORCEMENT": "true",
            "API_BIND_HOST": host,
            "BROKER_MODE": env.get("BROKER_MODE", "mock_ibkr_readonly"),
            "SCHEDULER_RUN_IN_API": "true",
            "PYTHONPATH": str(API_ROOT),
        }
    )

    proc = subprocess.Popen(
        [
            python_executable(),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            host,
            "--port",
            str(port),
            "--log-level",
            "info",
        ],
        cwd=API_ROOT,
        env=env,
    )

    base = f"http://{host}:{port}"
    try:
        wait_healthy(f"{base}/health")
        webbrowser.open(f"{base}/")
        print("PERSONAL_DESKTOP_RUNNING")
        print(f"UI:   {base}/")
        print(f"API:  {base}")
        print(f"DATA: {data_dir}")
        print("No login required. Press Ctrl+C to stop.")
        while True:
            code = proc.poll()
            if code is not None:
                raise SystemExit(f"API exited with code {code}")
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping…")
        return 0
    finally:
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
