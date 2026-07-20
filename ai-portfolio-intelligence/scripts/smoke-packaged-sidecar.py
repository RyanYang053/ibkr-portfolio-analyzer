#!/usr/bin/env python3
"""Smoke-test the PyInstaller portfolio-api sidecar (not the Python interpreter)."""

from __future__ import annotations

import json
import os
import platform
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
BINARIES = ROOT / "apps" / "desktop" / "src-tauri" / "binaries"


def rust_target_triple() -> str:
    try:
        return subprocess.check_output(["rustc", "--print", "host-tuple"], text=True).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        system = platform.system().lower()
        machine = platform.machine().lower()
        if system == "darwin":
            arch = "aarch64" if machine in {"arm64", "aarch64"} else "x86_64"
            return f"{arch}-apple-darwin"
        if system == "windows":
            return "x86_64-pc-windows-msvc"
        return "x86_64-unknown-linux-gnu"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http(url: str, *, token: str | None = None, method: str = "GET", body: bytes | None = None) -> tuple[int, str]:
    headers = {}
    if token:
        headers["X-Local-Session"] = token
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def main() -> int:
    suffix = ".exe" if platform.system() == "Windows" else ""
    sidecar = BINARIES / f"portfolio-api-{rust_target_triple()}{suffix}"
    if not sidecar.exists():
        raise SystemExit(f"Missing sidecar binary: {sidecar}")

    data_dir = Path(tempfile.mkdtemp(prefix="portfolio-sidecar-smoke-"))
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
            "LOCAL_API_HOST": host,
            "LOCAL_API_PORT": str(port),
            "LOCAL_SESSION_TOKEN": token,
            "DISABLE_AUTH_ENFORCEMENT": "true",
            "API_BIND_HOST": host,
            "BROKER_MODE": "mock_ibkr_readonly",
            "SCHEDULER_ENABLED": "false",
            "SCHEDULER_RUN_IN_API": "false",
        }
    )

    log_path = data_dir / "logs" / "sidecar.log"
    proc = subprocess.Popen(
        [str(sidecar)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://{host}:{port}"
    # Windows first-launch of a large onefile binary can be slow under AV scanning.
    attempts = 360 if platform.system() == "Windows" else 180
    try:
        healthy = False
        for _ in range(attempts):
            try:
                status, _ = http(f"{base}/health")
                if status == 200:
                    healthy = True
                    break
            except Exception:
                pass
            if proc.poll() is not None:
                detail = ""
                if log_path.exists():
                    detail = log_path.read_text(encoding="utf-8", errors="replace")
                raise SystemExit(
                    f"Sidecar exited early with code {proc.returncode}\n{detail}"
                )
            time.sleep(0.5)
        if not healthy:
            detail = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
            raise SystemExit(f"Packaged sidecar never became healthy\n{detail}")

        denied, _ = http(f"{base}/desktop/status")
        if denied != 401:
            raise SystemExit(f"Expected 401 without token, got {denied}")

        ok, body = http(f"{base}/desktop/status", token=token)
        if ok != 200:
            raise SystemExit(f"desktop/status failed: {ok} {body}")

        root_status, root_body = http(f"{base}/")
        if root_status not in {401, 404}:
            raise SystemExit(f"Root should require session, got {root_status}")
        if token in root_body or "__DESKTOP_RUNTIME__" in root_body:
            raise SystemExit("Session token disclosed by packaged sidecar")

        schema_status, schema_body = http(f"{base}/openapi.json", token=token)
        if schema_status == 200:
            paths = json.loads(schema_body).get("paths", {})
            for forbidden in ("/auth/login", "/auth/register", "/auth/bootstrap", "/auth/accept-invite"):
                if forbidden in paths:
                    raise SystemExit(f"Hosted auth route exposed in desktop mode: {forbidden}")
            if token in schema_body:
                raise SystemExit("Session token found in OpenAPI schema")

        export_status, export_body = http(f"{base}/desktop/export", token=token, method="POST")
        if export_status != 200 or "export_path" not in export_body:
            raise SystemExit(f"export failed: {export_status} {export_body}")

        require_keychain = platform.system() in {"Darwin", "Windows"}
        status_code, status_body = http(f"{base}/desktop/secrets/flex-token", token=token)
        if require_keychain and status_code != 200:
            raise SystemExit(f"keychain status failed: {status_code} {status_body}")
        if status_code == 200:
            probe = "smoke-flex-token-" + token_urlsafe(16)
            put_status, put_body = http(
                f"{base}/desktop/secrets/flex-token",
                token=token,
                method="PUT",
                body=json.dumps({"token": probe}).encode("utf-8"),
            )
            if require_keychain and put_status != 200:
                raise SystemExit(f"keychain put failed: {put_status} {put_body}")
            if put_status == 200:
                if probe in put_body:
                    raise SystemExit("Flex token value leaked in PUT response")
                got_status, got_body = http(f"{base}/desktop/secrets/flex-token", token=token)
                if got_status != 200:
                    raise SystemExit(f"keychain get status unexpected: {got_status} {got_body}")
                got_payload = json.loads(got_body)
                if got_payload.get("configured") is not True:
                    raise SystemExit(f"keychain get expected configured=true: {got_body}")
                if probe in got_body:
                    raise SystemExit("Flex token value leaked in GET response")
                del_status, del_body = http(
                    f"{base}/desktop/secrets/flex-token",
                    token=token,
                    method="DELETE",
                )
                if del_status != 200:
                    raise SystemExit(f"keychain delete failed: {del_status} {del_body}")
                if probe in del_body:
                    raise SystemExit("Flex token value leaked in DELETE response")
        elif require_keychain:
            raise SystemExit(f"keychain required on {platform.system()} but status={status_code}")

        print("PACKAGED_SIDECAR_SMOKE_OK")
        print(f"sidecar={sidecar}")
        print(f"port={port}")
        return 0
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
