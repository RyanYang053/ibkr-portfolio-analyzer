#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "openapi.json"
REQUIRED_PATHS = {
    "/portfolio/summary",
    "/portfolio/positions",
    "/portfolio/pnl-history",
    "/stocks/{symbol}/score",
    "/recommendations",
    "/health",
}


def main() -> int:
    subprocess.check_call([sys.executable, str(ROOT / "scripts" / "export_openapi.py")], cwd=ROOT)
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    paths = set(schema.get("paths", {}))
    missing = sorted(REQUIRED_PATHS - paths)
    if missing:
        print(f"OpenAPI schema missing required paths: {missing}")
        return 1
    components = schema.get("components", {}).get("schemas", {})
    position_names = [name for name in components if name == "Position"]
    if "Position" not in components:
        print("OpenAPI schema missing Position component")
        return 1
    print("OpenAPI schema contract check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
