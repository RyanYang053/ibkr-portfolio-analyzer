#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Canonical committed schema is always the hosted/development route set.
os.environ["DEPLOYMENT_MODE"] = "development"
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("PERSISTENCE_BACKEND", "json")

from app.main import app  # noqa: E402

OUTPUT = ROOT / "openapi.json"


def main() -> None:
    schema = app.openapi()
    OUTPUT.write_text(json.dumps(schema, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote OpenAPI schema to {OUTPUT}")


if __name__ == "__main__":
    main()
