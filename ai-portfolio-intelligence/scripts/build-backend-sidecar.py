#!/usr/bin/env python3
"""Build the FastAPI sidecar as a Tauri-compatible onefile binary."""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
SPEC = API_ROOT / "packaging" / "portfolio-api.spec"
DESKTOP_BINARIES = ROOT / "apps" / "desktop" / "src-tauri" / "binaries"


def rust_target_triple() -> str:
    try:
        return subprocess.check_output(
            ["rustc", "--print", "host-tuple"],
            text=True,
        ).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        system = platform.system().lower()
        machine = platform.machine().lower()
        if system == "darwin":
            arch = "aarch64" if machine in {"arm64", "aarch64"} else "x86_64"
            return f"{arch}-apple-darwin"
        if system == "windows":
            return "x86_64-pc-windows-msvc"
        return "x86_64-unknown-linux-gnu"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=DESKTOP_BINARIES)
    args = parser.parse_args()

    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            str(SPEC),
        ],
        cwd=API_ROOT,
    )

    built = API_ROOT / "dist" / ("portfolio-api.exe" if platform.system() == "Windows" else "portfolio-api")
    if not built.exists():
        # Some PyInstaller versions place onefile under dist/portfolio-api/portfolio-api
        nested = API_ROOT / "dist" / "portfolio-api" / built.name
        if nested.exists():
            built = nested
        else:
            raise SystemExit(f"Expected PyInstaller output missing: {built}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    triple = rust_target_triple()
    suffix = ".exe" if platform.system() == "Windows" else ""
    dest = args.out_dir / f"portfolio-api-{triple}{suffix}"
    shutil.copy2(built, dest)
    dest.chmod(dest.stat().st_mode | 0o111)
    print(f"Sidecar ready for Tauri: {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
