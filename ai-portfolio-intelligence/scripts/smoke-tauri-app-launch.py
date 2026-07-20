#!/usr/bin/env python3
"""Launch the packaged Tauri application and verify sidecar + API health.

This exercises the real desktop binary (not only the PyInstaller sidecar).
"""

from __future__ import annotations

import argparse
import os
import platform
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "apps" / "desktop" / "src-tauri"


def http_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def listening_ports() -> set[int]:
    ports: set[int] = set()
    system = platform.system()
    try:
        if system == "Windows":
            output = subprocess.check_output(
                ["netstat", "-ano"],
                text=True,
                errors="replace",
            )
            for line in output.splitlines():
                if "LISTENING" not in line or "127.0.0.1:" not in line:
                    continue
                parts = line.split()
                if len(parts) < 2:
                    continue
                local = parts[1]
                if local.startswith("127.0.0.1:"):
                    try:
                        ports.add(int(local.rsplit(":", 1)[1]))
                    except ValueError:
                        pass
        else:
            output = subprocess.check_output(
                ["lsof", "-nP", "-iTCP@127.0.0.1", "-sTCP:LISTEN"],
                text=True,
                errors="replace",
            )
            for line in output.splitlines()[1:]:
                if ":" not in line:
                    continue
                try:
                    port = int(line.rsplit(":", 1)[-1].split()[0])
                    ports.add(port)
                except ValueError:
                    continue
    except (FileNotFoundError, subprocess.CalledProcessError):
        return ports
    return ports


def find_app_binary(target: str) -> Path:
    release_dirs = [
        DESKTOP / "target" / target / "release",
        DESKTOP / "target" / "release",
    ]
    bundle_roots = [path / "bundle" for path in release_dirs]
    system = platform.system()
    candidates: list[Path] = []

    for release_dir in release_dirs:
        if not release_dir.exists():
            continue
        if system == "Darwin":
            candidates.extend(release_dir.glob("Portfolio Analyzer"))
            candidates.extend(release_dir.glob("portfolio-analyzer"))
        elif system == "Windows":
            candidates.extend(release_dir.glob("Portfolio Analyzer.exe"))
            candidates.extend(release_dir.glob("portfolio-analyzer.exe"))
        else:
            candidates.extend(release_dir.glob("portfolio-analyzer"))
            candidates.extend(release_dir.glob("Portfolio Analyzer"))

    for root in bundle_roots:
        if not root.exists():
            continue
        if system == "Darwin":
            candidates.extend(root.rglob("Portfolio Analyzer.app/Contents/MacOS/Portfolio Analyzer"))
        elif system == "Windows":
            candidates.extend(
                path
                for path in root.rglob("*.exe")
                if "setup" not in path.name.lower() and "uninstall" not in path.name.lower()
            )
        else:
            candidates.extend(root.rglob("*.AppImage"))

    ranked = sorted(
        {path.resolve() for path in candidates if path.is_file()},
        key=lambda path: (
            0 if "bundle" not in str(path) else 1,
            0 if "setup" not in path.name.lower() else 2,
            len(str(path)),
        ),
    )
    if not ranked:
        raise SystemExit(
            "No packaged Portfolio Analyzer binary found under "
            f"{DESKTOP / 'target'}. Build installers first."
        )
    return ranked[0]


def terminate(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    try:
        if platform.system() == "Windows":
            proc.terminate()
        else:
            os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            if platform.system() == "Windows":
                proc.kill()
            else:
                os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True, help="Rust target triple used for the build")
    parser.add_argument("--timeout-seconds", type=int, default=120)
    args = parser.parse_args()

    binary = find_app_binary(args.target)
    data_dir = Path(tempfile.mkdtemp(prefix="portfolio-tauri-launch-"))
    before_ports = listening_ports()

    env = os.environ.copy()
    env["PORTFOLIO_DATA_DIR"] = str(data_dir)
    env["RUST_LOG"] = "info"

    print(f"Launching {binary}")
    print(f"data_dir={data_dir}")

    popen_kwargs: dict = {
        "env": env,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if platform.system() != "Windows":
        popen_kwargs["start_new_session"] = True
    if platform.system() == "Linux" and binary.suffix == ".AppImage":
        binary.chmod(binary.stat().st_mode | 0o111)

    proc = subprocess.Popen([str(binary)], **popen_kwargs)
    deadline = time.time() + args.timeout_seconds
    healthy_url = None
    try:
        while time.time() < deadline:
            if proc.poll() is not None:
                log_path = data_dir / "logs" / "sidecar.log"
                detail = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
                raise SystemExit(
                    f"Desktop app exited early with code {proc.returncode}\n{detail}"
                )

            new_ports = listening_ports() - before_ports
            for port in sorted(new_ports):
                url = f"http://127.0.0.1:{port}/health"
                if http_ok(url):
                    healthy_url = url
                    break
            if healthy_url:
                break
            # Also probe common case where sidecar reused an existing listener set.
            for port in sorted(listening_ports()):
                url = f"http://127.0.0.1:{port}/health"
                if http_ok(url):
                    # Confirm this looks like our API.
                    try:
                        with urllib.request.urlopen(
                            f"http://127.0.0.1:{port}/version",
                            timeout=2,
                        ) as response:
                            body = response.read().decode("utf-8", errors="replace")
                        if "version" in body or response.status == 200:
                            healthy_url = f"http://127.0.0.1:{port}/health"
                            break
                    except Exception:
                        continue
            if healthy_url:
                break
            time.sleep(1.0)

        if not healthy_url:
            log_path = data_dir / "logs" / "sidecar.log"
            detail = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
            raise SystemExit(f"Desktop app launched but local API never became healthy\n{detail}")

        # Missing token must fail closed for protected routes.
        try:
            urllib.request.urlopen(healthy_url.replace("/health", "/desktop/status"), timeout=3)
            raise SystemExit("desktop/status unexpectedly public after app launch")
        except urllib.error.HTTPError as exc:
            if exc.code != 401:
                raise SystemExit(f"Expected 401 for desktop/status, got {exc.code}")

        print("TAURI_APP_LAUNCH_SMOKE_OK")
        print(f"binary={binary}")
        print(f"health={healthy_url}")
        print(f"data_dir={data_dir}")
        return 0
    finally:
        terminate(proc)
        # Best-effort cleanup of residual sidecar children.
        time.sleep(1.0)


if __name__ == "__main__":
    raise SystemExit(main())
