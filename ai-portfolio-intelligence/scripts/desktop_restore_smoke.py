#!/usr/bin/env python3
"""Export → restore → repository read smoke for desktop JSON state."""

from __future__ import annotations

import hashlib
import json
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
import zipfile
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
        with urllib.request.urlopen(request, timeout=8) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sqlite_env(data_dir: Path) -> dict:
    """Match the packaged desktop app: SQLite canonical store at <data_dir>/portfolio.db."""
    env = os.environ.copy()
    env.update(
        {
            "DEPLOYMENT_MODE": "desktop_local",
            "ENVIRONMENT": "desktop",
            "PERSISTENCE_BACKEND": "sqlite",
            "DATABASE_URL": f"sqlite+pysqlite:///{data_dir / 'portfolio.db'}",
            "PORTFOLIO_DATA_DIR": str(data_dir),
            "PYTHONPATH": str(API_ROOT),
        }
    )
    return env


def seed_application_state(data_dir: Path) -> None:
    script = r"""
from app.db.state_store import get_state_store
store = get_state_store()
store.write_json("holding_theses", "U0001:AAPL", {"summary": "Quality compounder"})
store.write_json("watchlist", "local-owner", {"symbols": ["AAPL"]})
store.write_json("broker", "runtime_config", {"mode": "mock_ibkr_readonly", "host": "127.0.0.1"})
store.write_json("investor_profile", "local-owner", {"risk_tolerance": "moderate"})
print("SEEDED")
"""
    subprocess.check_call(
        [python_executable(), "-c", script],
        cwd=API_ROOT,
        env=sqlite_env(data_dir),
    )


def read_application_state(data_dir: Path) -> dict:
    script = r"""
import json
from app.db.state_store import get_state_store
store = get_state_store()
payload = {
    "thesis": store.read_json("holding_theses", "U0001:AAPL"),
    "watchlist": store.read_json("watchlist", "local-owner"),
    "broker": store.read_json("broker", "runtime_config"),
    "profile": store.read_json("investor_profile", "local-owner"),
}
print(json.dumps(payload))
"""
    raw = subprocess.check_output(
        [python_executable(), "-c", script],
        cwd=API_ROOT,
        env=sqlite_env(data_dir),
        text=True,
    ).strip()
    return json.loads(raw.splitlines()[-1])


def start_api(data_dir: Path, token: str, port: int) -> tuple[subprocess.Popen[str], Path]:
    log_path = data_dir / "uvicorn.log"
    env = sqlite_env(data_dir)
    env.update(
        {
            "LOCAL_API_HOST": "127.0.0.1",
            "LOCAL_API_PORT": str(port),
            "LOCAL_SESSION_TOKEN": token,
            "DISABLE_AUTH_ENFORCEMENT": "true",
            "API_BIND_HOST": "127.0.0.1",
            "BROKER_MODE": "mock_ibkr_readonly",
            "SCHEDULER_ENABLED": "false",
            "SCHEDULER_RUN_IN_API": "false",
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
            "127.0.0.1",
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
    return proc, log_path


def wait_healthy(base: str, proc: subprocess.Popen[str], log_path: Path) -> None:
    for _ in range(80):
        try:
            status, _ = http_json(f"{base}/health")
            if status == 200:
                return
        except Exception:
            pass
        if proc.poll() is not None:
            raise SystemExit(f"API exited early:\n{log_path.read_text(encoding='utf-8', errors='replace')}")
        time.sleep(0.25)
    raise SystemExit(f"API never became healthy\n{log_path.read_text(encoding='utf-8', errors='replace')}")


def stop_api(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def validate_export_manifest(export_zip: Path, extract_root: Path) -> dict:
    with zipfile.ZipFile(export_zip, "r") as archive:
        archive.extractall(extract_root)
        manifest_raw = archive.read("export-manifest.json").decode("utf-8")

    manifest = json.loads(manifest_raw)
    if manifest.get("schema_version") != 1:
        raise SystemExit(f"Unexpected schema_version: {manifest.get('schema_version')}")
    if not isinstance(manifest.get("files"), list):
        raise SystemExit("export-manifest.json missing files list")

    for entry in manifest["files"]:
        relative = entry["path"]
        expected = entry["sha256"]
        target = extract_root / relative
        if not target.is_file():
            raise SystemExit(f"Missing restored file: {relative}")
        actual = sha256_file(target)
        if actual != expected:
            raise SystemExit(f"Hash mismatch for {relative}: {actual} != {expected}")
        if target.stat().st_size != entry["size_bytes"]:
            raise SystemExit(f"Size mismatch for {relative}")

    return manifest


def main() -> int:
    source_dir = Path(tempfile.mkdtemp(prefix="portfolio-restore-src-"))
    restored_dir = Path(tempfile.mkdtemp(prefix="portfolio-restore-dst-"))
    extract_dir = Path(tempfile.mkdtemp(prefix="portfolio-restore-extract-"))
    token = token_urlsafe(32)
    port = free_port()
    proc = None

    try:
        seed_application_state(source_dir)
        before = read_application_state(source_dir)
        if before["thesis"]["summary"] != "Quality compounder":
            raise SystemExit("Seeded thesis missing via JsonStateStore")

        proc, log_path = start_api(source_dir, token, port)
        base = f"http://127.0.0.1:{port}"
        wait_healthy(base, proc, log_path)

        export_status, export_body = http_json(f"{base}/desktop/export", token=token, method="POST")
        if export_status != 200:
            raise SystemExit(f"export failed: {export_status} {export_body}")
        export_payload = json.loads(export_body)
        export_path = Path(export_payload["export_path"])
        if not export_path.is_file():
            raise SystemExit(f"export zip missing: {export_path}")

        stop_api(proc)
        proc = None

        manifest = validate_export_manifest(export_path, extract_dir)

        # P0.5: under SQLite the canonical DB (portfolio.db) MUST be in the export.
        manifest_paths = {entry["path"] for entry in manifest["files"]}
        if "portfolio.db" not in manifest_paths:
            raise SystemExit(f"Export omitted portfolio.db under SQLite backend: {sorted(manifest_paths)}")

        for folder in ("state", "imports"):
            src = extract_dir / folder
            if src.exists():
                shutil.copytree(src, restored_dir / folder, dirs_exist_ok=True)
        # Restore the canonical database itself.
        restored_db = extract_dir / "portfolio.db"
        if restored_db.exists():
            shutil.copy2(restored_db, restored_dir / "portfolio.db")

        after = read_application_state(restored_dir)
        if after != before:
            raise SystemExit(f"Restored repository state mismatch: {after} != {before}")

        restored_port = free_port()
        restored_token = token_urlsafe(32)
        proc, log_path = start_api(restored_dir, restored_token, restored_port)
        restored_base = f"http://127.0.0.1:{restored_port}"
        wait_healthy(restored_base, proc, log_path)

        status_code, status_body = http_json(f"{restored_base}/desktop/status", token=restored_token)
        if status_code != 200 or "desktop_local" not in status_body:
            raise SystemExit(f"restored desktop/status failed: {status_code} {status_body}")

        print("DESKTOP_RESTORE_SMOKE_OK")
        print(f"files_validated={len(manifest['files'])}")
        print(f"export_path={export_path}")
        print(f"restored_dir={restored_dir}")
        return 0
    finally:
        if proc is not None:
            stop_api(proc)
        if os.getenv("DESKTOP_SMOKE_KEEP_DATA") != "1":
            shutil.rmtree(source_dir, ignore_errors=True)
            shutil.rmtree(restored_dir, ignore_errors=True)
            shutil.rmtree(extract_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
