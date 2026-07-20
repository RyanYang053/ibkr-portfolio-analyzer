#!/usr/bin/env python3
"""Desktop-local personal smoke: loopback API + session token + export (no Docker)."""

from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
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


def http_json(url: str, *, token: str | None = None, method: str = "GET") -> tuple[int, str]:
    headers = {}
    if token:
        headers["X-Local-Session"] = token
    request = urllib.request.Request(url, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def main() -> int:
    data_dir = Path(tempfile.mkdtemp(prefix="portfolio-desktop-smoke-"))
    log_path = data_dir / "uvicorn.log"
    host = "127.0.0.1"
    port = free_port()
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
            "BROKER_MODE": "mock_ibkr_readonly",
            "SCHEDULER_ENABLED": "false",
            "SCHEDULER_RUN_IN_API": "false",
            "PYTHONPATH": str(API_ROOT),
        }
    )

    log_handle = log_path.open("w", encoding="utf-8")
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
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )

    base = f"http://{host}:{port}"
    try:
        healthy = False
        for _ in range(80):
            try:
                status, _ = http_json(f"{base}/health")
                if status == 200:
                    healthy = True
                    break
            except Exception:
                pass
            if proc.poll() is not None:
                log_handle.flush()
                raise SystemExit(f"API exited early:\n{log_path.read_text(encoding='utf-8', errors='replace')}")
            time.sleep(0.25)
        if not healthy:
            log_handle.flush()
            raise SystemExit(f"API never became healthy\n{log_path.read_text(encoding='utf-8', errors='replace')}")

        denied_status, _ = http_json(f"{base}/desktop/status")
        if denied_status != 401:
            raise SystemExit(f"Expected 401 without session, got {denied_status}")

        ok_status, body = http_json(f"{base}/desktop/status", token=token)
        if ok_status != 200 or "desktop_local" not in body:
            raise SystemExit(f"desktop/status failed: {ok_status} {body}")

        ui_status, ui_body = http_json(f"{base}/")
        if ui_status != 200 or "Portfolio Analyzer" not in ui_body:
            raise SystemExit(f"desktop UI failed: {ui_status}")
        if "__DESKTOP_RUNTIME__" not in ui_body:
            raise SystemExit("desktop UI missing runtime injection")

        export_status, export_body = http_json(
            f"{base}/desktop/export",
            token=token,
            method="POST",
        )
        if export_status != 200 or "export_path" not in export_body:
            raise SystemExit(f"desktop/export failed: {export_status} {export_body}")

        if not (data_dir / "backups").exists():
            raise SystemExit("Expected backups directory after desktop bootstrap")

        print("DESKTOP_LOCAL_SMOKE_OK")
        print(f"port={port}")
        print(f"data_dir={data_dir}")
        print(f"status={body}")
        print(f"export={export_body}")
        return 0
    finally:
        log_handle.close()
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        if os.getenv("DESKTOP_SMOKE_KEEP_DATA") != "1":
            shutil.rmtree(data_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
