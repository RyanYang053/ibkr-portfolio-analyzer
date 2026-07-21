#!/usr/bin/env python3
"""Launch the packaged Tauri installer/bundle and verify UI + sidecar lifecycle.

Prefers real distribution artifacts:
- macOS: .app/Contents/MacOS/...
- Linux: .AppImage
- Windows: silent NSIS install into a temp directory, then installed .exe
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
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


def http_status(url: str, *, token: str | None = None, method: str = "GET") -> tuple[int, str]:
    headers = {}
    if token:
        headers["X-Local-Session"] = token
    request = urllib.request.Request(url, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return 0, str(exc)


def listening_ports() -> set[int]:
    ports: set[int] = set()
    system = platform.system()
    try:
        if system == "Windows":
            output = subprocess.check_output(["netstat", "-ano"], text=True, errors="replace")
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
                    ports.add(int(line.rsplit(":", 1)[-1].split()[0]))
                except ValueError:
                    continue
    except (FileNotFoundError, subprocess.CalledProcessError):
        return ports
    return ports


def bundle_roots(target: str) -> list[Path]:
    return [
        DESKTOP / "target" / target / "release" / "bundle",
        DESKTOP / "target" / "release" / "bundle",
    ]


def find_macos_app_binary(target: str) -> Path:
    apps: list[Path] = []
    for root in bundle_roots(target):
        if root.exists():
            apps.extend(root.rglob("Portfolio Analyzer.app"))
    if not apps:
        raise SystemExit("No macOS .app bundle found under target/*/release/bundle")
    app = sorted(apps, key=lambda path: path.stat().st_mtime, reverse=True)[0]
    binary = app / "Contents" / "MacOS" / "Portfolio Analyzer"
    if not binary.is_file():
        # Some builds use a different binary name.
        macos_dir = app / "Contents" / "MacOS"
        executables = [path for path in macos_dir.iterdir() if path.is_file()]
        if not executables:
            raise SystemExit(f"No executable inside {app}")
        binary = executables[0]
    return binary


def find_linux_appimage(target: str) -> Path:
    images: list[Path] = []
    for root in bundle_roots(target):
        if root.exists():
            images.extend(root.rglob("*.AppImage"))
    if not images:
        raise SystemExit("No Linux AppImage found under target/*/release/bundle")
    image = sorted(images, key=lambda path: path.stat().st_mtime, reverse=True)[0]
    image.chmod(image.stat().st_mode | 0o111)
    return image


def find_windows_nsis_installer(target: str) -> Path:
    installers: list[Path] = []
    for root in bundle_roots(target):
        if not root.exists():
            continue
        installers.extend(
            path
            for path in root.rglob("*.exe")
            if "setup" in path.name.lower() or "nsis" in str(path).lower()
        )
    if not installers:
        # Fallback: any non-uninstall exe under bundle/nsis
        for root in bundle_roots(target):
            nsis = root / "nsis"
            if nsis.exists():
                installers.extend(
                    path
                    for path in nsis.glob("*.exe")
                    if "uninstall" not in path.name.lower()
                )
    if not installers:
        raise SystemExit("No Windows NSIS installer found under target/*/release/bundle")
    return sorted(installers, key=lambda path: path.stat().st_mtime, reverse=True)[0]


def silent_install_windows(installer: Path, install_dir: Path) -> Path:
    install_dir.mkdir(parents=True, exist_ok=True)
    # NSIS silent install; /D= must be last and unquoted per NSIS rules.
    cmd = [str(installer), "/S", f"/D={install_dir}"]
    print(f"Silent NSIS install: {cmd}")
    completed = subprocess.run(cmd, check=False)
    if completed.returncode not in {0, None}:
        # Some NSIS builds return 0 asynchronously; wait for files.
        pass
    deadline = time.time() + 120
    while time.time() < deadline:
        candidates = list(install_dir.rglob("Portfolio Analyzer.exe")) + list(
            install_dir.rglob("portfolio-analyzer.exe")
        )
        if candidates:
            return candidates[0]
        time.sleep(1.0)
    raise SystemExit(f"NSIS silent install did not produce an executable under {install_dir}")


def resolve_launch_binary(target: str, work_dir: Path) -> Path:
    system = platform.system()
    if system == "Darwin":
        return find_macos_app_binary(target)
    if system == "Linux":
        return find_linux_appimage(target)
    if system == "Windows":
        installer = find_windows_nsis_installer(target)
        install_dir = work_dir / "installed"
        return silent_install_windows(installer, install_dir)
    raise SystemExit(f"Unsupported platform: {system}")


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


def wait_for_port_closed(port: int, timeout_seconds: float = 30.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if port not in listening_ports():
            # Confirm health is gone.
            status, _ = http_status(f"http://127.0.0.1:{port}/health")
            if status == 0:
                return
        time.sleep(0.5)
    raise SystemExit(f"Sidecar port {port} remained open after parent exit")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=480)
    args = parser.parse_args()

    work_dir = Path(tempfile.mkdtemp(prefix="portfolio-tauri-launch-"))
    data_dir = work_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    binary = resolve_launch_binary(args.target, work_dir)
    before_ports = listening_ports()

    env = os.environ.copy()
    env["PORTFOLIO_DATA_DIR"] = str(data_dir)
    env["RUST_LOG"] = "info"

    print(f"Launching packaged binary: {binary}")
    print(f"data_dir={data_dir}")

    popen_kwargs: dict = {
        "env": env,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if platform.system() != "Windows":
        popen_kwargs["start_new_session"] = True

    proc = subprocess.Popen([str(binary)], **popen_kwargs)
    deadline = time.time() + args.timeout_seconds
    healthy_url = None
    api_port: int | None = None

    try:
        while time.time() < deadline:
            if proc.poll() is not None:
                log_path = data_dir / "logs" / "sidecar.log"
                detail = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
                raise SystemExit(f"Desktop app exited early with code {proc.returncode}\n{detail}")

            for port in sorted(listening_ports() - before_ports):
                status, _ = http_status(f"http://127.0.0.1:{port}/health")
                if status == 200:
                    healthy_url = f"http://127.0.0.1:{port}/health"
                    api_port = port
                    break
            if healthy_url:
                break
            time.sleep(1.0)

        if not healthy_url or api_port is None:
            log_path = data_dir / "logs" / "sidecar.log"
            detail = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
            raise SystemExit(f"Packaged app launched but local API never became healthy\n{detail}")

        denied, _ = http_status(healthy_url.replace("/health", "/desktop/status"))
        if denied != 401:
            raise SystemExit(f"Expected 401 for desktop/status without token, got {denied}")

        # Frontend readiness: protected UI posts /desktop/ui-ready after runtime injection.
        ui_marker = data_dir / "ui-ready.json"
        while time.time() < deadline:
            if ui_marker.is_file():
                payload = json.loads(ui_marker.read_text(encoding="utf-8"))
                if payload.get("ready") is True:
                    break
            if proc.poll() is not None:
                raise SystemExit("Desktop app exited before UI readiness marker")
            time.sleep(1.0)
        else:
            raise SystemExit(
                "UI readiness marker missing: webview did not report /desktop/ui-ready"
            )

        print("TAURI_APP_LAUNCH_SMOKE_OK")
        print(f"binary={binary}")
        print(f"health={healthy_url}")
        print(f"ui_ready={ui_marker}")
        print(f"data_dir={data_dir}")
        return 0
    finally:
        terminate(proc)
        if api_port is not None:
            try:
                wait_for_port_closed(api_port, timeout_seconds=45)
                print(f"sidecar_port_closed={api_port}")
            except SystemExit as exc:
                # Surface after cleanup attempt.
                print(str(exc), file=sys.stderr)
                raise
        if os.getenv("DESKTOP_SMOKE_KEEP_DATA") != "1":
            shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
