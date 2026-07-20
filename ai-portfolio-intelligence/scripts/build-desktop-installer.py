#!/usr/bin/env python3
"""Build the desktop installer: API sidecar, Next static export, and Tauri bundle."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "apps" / "desktop"
WEB_OUT = ROOT / "apps" / "web" / "out"
BUNDLE = DESKTOP / "src-tauri" / "target" / "release" / "bundle"
APP = BUNDLE / "macos" / "Portfolio Analyzer.app"
DMG_DIR = BUNDLE / "dmg"
DMG = DMG_DIR / "Portfolio Analyzer_0.1.0_aarch64.dmg"


def run(cmd: list[str], *, cwd: Path | None = None) -> None:
    subprocess.check_call(cmd, cwd=cwd or ROOT)


def build_dmg() -> None:
    if not APP.exists():
        raise SystemExit(f"Expected app bundle missing: {APP}")
    DMG_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pa-dmg-") as stage:
        stage_path = Path(stage)
        shutil.copytree(APP, stage_path / APP.name)
        applications = stage_path / "Applications"
        if not applications.exists():
            applications.symlink_to("/Applications")
        if DMG.exists():
            DMG.unlink()
        subprocess.check_call(
            [
                "hdiutil",
                "create",
                "-volname",
                "Portfolio Analyzer",
                "-srcfolder",
                str(stage_path),
                "-ov",
                "-format",
                "UDZO",
                str(DMG),
            ]
        )
    print(f"DMG ready: {DMG}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-sidecar", action="store_true")
    parser.add_argument("--skip-web", action="store_true")
    parser.add_argument("--skip-dmg", action="store_true")
    args = parser.parse_args()

    if not args.skip_sidecar:
        run([sys.executable, "scripts/build-backend-sidecar.py"])

    if not args.skip_web or not WEB_OUT.exists():
        run([sys.executable, "scripts/prepare-tauri-binaries.py"])

    run(["npm", "install"], cwd=DESKTOP)
    run(["npx", "tauri", "build"], cwd=DESKTOP)

    if not args.skip_dmg:
        # create-dmg fails on paths with spaces; hdiutil is reliable.
        build_dmg()

    print("Desktop installer build complete")
    print(f"App: {APP}")
    if DMG.exists():
        print(f"DMG: {DMG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
