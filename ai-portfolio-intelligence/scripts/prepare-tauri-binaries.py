#!/usr/bin/env python3
"""Prepare a static-export-compatible Next.js tree for the desktop app.

Builds under /tmp when the repo lives on a slow volume (e.g. iCloud Documents),
then copies apps/web/out back into the workspace for Tauri bundling.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web"
TAURI_BINARIES = ROOT / "apps" / "desktop" / "src-tauri" / "binaries"
WEB_OUT = WEB / "out"
BACKUP = WEB / ".desktop-build-backup"


def npm_executable() -> str:
    candidates = ("npm.cmd", "npm.exe", "npm") if os.name == "nt" else ("npm",)
    for name in candidates:
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit("npm was not found on PATH")


def run(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    subprocess.check_call(cmd, cwd=cwd, env=merged)


def npm_run(script: str, *, cwd: Path, env: dict[str, str] | None = None) -> None:
    run([npm_executable(), "run", script], cwd=cwd, env=env)


def npm_install(*, cwd: Path, env: dict[str, str] | None = None) -> None:
    run([npm_executable(), "install", "--no-fund", "--no-audit"], cwd=cwd, env=env)


def rust_target_triple() -> str:
    try:
        return subprocess.check_output(["rustc", "--print", "host-tuple"], text=True).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        import platform

        system = platform.system().lower()
        machine = platform.machine().lower()
        if system == "darwin":
            arch = "aarch64" if machine in {"arm64", "aarch64"} else "x86_64"
            return f"{arch}-apple-darwin"
        if system == "windows":
            return "x86_64-pc-windows-msvc"
        return "x86_64-unknown-linux-gnu"


def backup_incompatible_paths(web_root: Path, backup_root: Path) -> None:
    if backup_root.exists():
        shutil.rmtree(backup_root)
    backup_root.mkdir(parents=True)

    for relative in ("middleware.ts", "app/api"):
        source = web_root / relative
        if source.exists():
            destination = backup_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))


def restore_backup(web_root: Path, backup_root: Path) -> None:
    if not backup_root.exists():
        return
    for path in sorted(backup_root.rglob("*"), reverse=True):
        if path.is_dir():
            continue
        relative = path.relative_to(backup_root)
        target = web_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        shutil.move(str(path), str(target))
    shutil.rmtree(backup_root, ignore_errors=True)


def install_spa_fallback(out_dir: Path) -> None:
    index = out_dir / "index.html"
    fallback = out_dir / "404.html"
    if index.exists() and not fallback.exists():
        shutil.copy2(index, fallback)


def copy_web_sources(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    ignore = shutil.ignore_patterns(
        "node_modules",
        ".next",
        "out",
        ".desktop-build-backup",
        "*.log",
        "dev_*.log",
    )
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(WEB, dest, ignore=ignore)


def build_static_export(*, use_temp: bool) -> None:
    env = {
        "NEXT_PUBLIC_DEPLOYMENT_MODE": "desktop_local",
        "NEXT_TELEMETRY_DISABLED": "1",
        "NODE_OPTIONS": os.environ.get("NODE_OPTIONS", "--max-old-space-size=8192"),
    }

    if not use_temp:
        try:
            backup_incompatible_paths(WEB, BACKUP)
            npm_run("build", cwd=WEB, env=env)
            install_spa_fallback(WEB_OUT)
        finally:
            restore_backup(WEB, BACKUP)
        return

    with tempfile.TemporaryDirectory(prefix="pa-desktop-web-") as tmp:
        tmp_root = Path(tmp)
        tmp_web = tmp_root / "web"
        copy_web_sources(tmp_web)
        backup_incompatible_paths(tmp_web, tmp_web / ".desktop-build-backup")
        npm_install(cwd=tmp_web, env=env)
        npm_run("build", cwd=tmp_web, env=env)
        tmp_out = tmp_web / "out"
        if not tmp_out.exists():
            raise SystemExit(f"Expected static export at {tmp_out}")
        install_spa_fallback(tmp_out)
        if WEB_OUT.exists():
            shutil.rmtree(WEB_OUT)
        shutil.copytree(tmp_out, WEB_OUT)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-web-build", action="store_true")
    parser.add_argument("--no-require-sidecar", action="store_true")
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Build inside apps/web instead of a /tmp copy (slower on iCloud Documents).",
    )
    args = parser.parse_args()

    TAURI_BINARIES.mkdir(parents=True, exist_ok=True)

    if not args.skip_web_build:
        use_temp = not args.in_place
        # Default to temp when the repo path looks like macOS Documents (often iCloud-backed).
        if "Documents" in str(WEB) and not args.in_place:
            use_temp = True
        print(f"Building desktop static export ({'temp copy' if use_temp else 'in-place'})…")
        build_static_export(use_temp=use_temp)
        if not WEB_OUT.exists():
            raise SystemExit("Expected apps/web/out after desktop static export")

    triple = rust_target_triple()
    suffix = ".exe" if os.name == "nt" else ""
    sidecar = TAURI_BINARIES / f"portfolio-api-{triple}{suffix}"
    if not args.no_require_sidecar and not sidecar.exists():
        raise SystemExit(
            f"Required Tauri sidecar is missing: {sidecar}. "
            "Run python scripts/build-backend-sidecar.py first."
        )

    print("Desktop prepare complete")
    print(f"static_export={'ok' if WEB_OUT.exists() else 'missing'}")
    print(f"sidecar={'ok' if sidecar.exists() else 'missing'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
