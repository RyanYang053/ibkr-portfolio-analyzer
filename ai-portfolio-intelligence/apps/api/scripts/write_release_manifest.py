#!/usr/bin/env python3
"""Write release-manifest.json for exact-SHA release certification."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "release-manifest.json"


def _git_sha() -> str:
    for key in ("GIT_SHA", "GITHUB_SHA"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return "unknown"


def _alembic_head() -> str | None:
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        config = Config(str(ROOT / "alembic.ini"))
        script = ScriptDirectory.from_config(config)
        return script.get_current_head()
    except Exception as exc:  # pragma: no cover - defensive
        return f"error:{exc.__class__.__name__}"


def _methodology_approvals() -> list[dict[str, object]]:
    sys.path.insert(0, str(ROOT))
    from app.services.methodology_registry import list_methodologies

    return [
        {
            "methodology_id": item.get("methodology_id"),
            "version": item.get("version"),
            "approval_status": item.get("approval_status"),
            "effective_date": item.get("effective_date"),
        }
        for item in list_methodologies()
    ]


def _methodology_digest(approvals: list[dict[str, object]]) -> str:
    canonical = sorted(approvals, key=lambda item: str(item.get("methodology_id") or ""))
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def certification_status(
    *,
    code_sha: str,
    pytest_report_sha256: str | None,
    golden_fixture_sha256: str | None,
    container_digest: str | None,
) -> dict[str, object]:
    blockers: list[str] = []
    if not code_sha or code_sha == "unknown":
        blockers.append("code_sha_unknown")
    if not pytest_report_sha256:
        blockers.append("pytest_report_digest_missing")
    if not golden_fixture_sha256:
        blockers.append("golden_fixture_digest_missing")
    if not container_digest or container_digest == "placeholder":
        blockers.append("container_digest_placeholder")
    return {
        "certified": not blockers,
        "blockers": blockers,
    }


def build_manifest(
    *,
    pytest_report: Path | None = None,
    golden_hash_file: Path | None = None,
    container_digest: str | None = None,
) -> dict[str, object]:
    approvals = _methodology_approvals()
    code_sha = _git_sha()
    pytest_digest = _file_sha256(pytest_report) if pytest_report else None
    golden_digest = _file_sha256(golden_hash_file) if golden_hash_file else None
    resolved_container = container_digest or os.environ.get("CONTAINER_DIGEST") or "placeholder"
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "code_sha": code_sha,
        "alembic_head": _alembic_head(),
        "app_version": "0.1.0",
        "environment": os.environ.get("ENVIRONMENT", "ci"),
        "methodology_registry_digest": _methodology_digest(approvals),
        "methodology_approvals": approvals,
        "pytest_report_sha256": pytest_digest,
        "golden_fixture_sha256": golden_digest,
        "container_digest": resolved_container,
        "certification": certification_status(
            code_sha=code_sha,
            pytest_report_sha256=pytest_digest,
            golden_fixture_sha256=golden_digest,
            container_digest=resolved_container,
        ),
        "approval_status": {
            "all_experimental_or_approved": all(
                str(item.get("approval_status") or "") in {"experimental", "approved"}
                for item in approvals
            ),
            "approved_count": sum(1 for item in approvals if item.get("approval_status") == "approved"),
            "experimental_count": sum(
                1 for item in approvals if item.get("approval_status") == "experimental"
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Write release-manifest.json")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--pytest-report", type=Path, default=None)
    parser.add_argument("--golden-hash-file", type=Path, default=None)
    parser.add_argument("--container-digest", type=str, default=None)
    parser.add_argument(
        "--require-certified",
        action="store_true",
        help="Exit non-zero unless code SHA and digests are present (container may remain placeholder).",
    )
    parser.add_argument(
        "--allow-placeholder-container",
        action="store_true",
        default=True,
        help="Treat container_digest=placeholder as non-blocking when --require-certified.",
    )
    args = parser.parse_args()

    manifest = build_manifest(
        pytest_report=args.pytest_report,
        golden_hash_file=args.golden_hash_file,
        container_digest=args.container_digest,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}")

    if args.require_certified:
        blockers = list(manifest["certification"]["blockers"])  # type: ignore[index]
        if args.allow_placeholder_container:
            blockers = [item for item in blockers if item != "container_digest_placeholder"]
        if blockers:
            print(f"Release manifest not certifiable: {blockers}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
