#!/usr/bin/env python3
"""Run valuation golden fixtures and optionally promote personal-use approvals."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _write_digest(out: Path, fixture_paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(fixture_paths):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    hexdigest = digest.hexdigest()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(hexdigest + "\n", encoding="utf-8")
    return hexdigest


def main() -> int:
    parser = argparse.ArgumentParser(description="Golden fixture runner / personal-use promote")
    parser.add_argument("--promote", action="store_true", help="Record personal-use approvals after pass")
    parser.add_argument(
        "--digest-out",
        type=Path,
        default=ROOT / "tests" / "fixtures" / "golden.sha256",
        help="Write combined golden fixture digest",
    )
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    from app.services.validation.golden_fixtures import (
        VALUATION_MODEL_IDS,
        _fixture_path,
        promote_personal_use_after_goldens,
        run_all_valuation_goldens,
    )

    fixtures = [_fixture_path(mid) for mid in VALUATION_MODEL_IDS]
    digest = _write_digest(args.digest_out, [p for p in fixtures if p.exists()])

    if args.promote:
        results = promote_personal_use_after_goldens()
    else:
        results = run_all_valuation_goldens()

    payload = {
        "golden_fixture_sha256": digest,
        "digest_path": str(args.digest_out),
        "results": results,
        "all_ok": all(bool(item.get("ok")) for item in results),
        "promoted": args.promote,
    }
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
