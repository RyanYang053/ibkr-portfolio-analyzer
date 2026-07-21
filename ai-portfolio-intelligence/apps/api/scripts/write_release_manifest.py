#!/usr/bin/env python3
"""Write release-manifest.json for exact-SHA release certification."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT = ROOT / "release-manifest.json"

# Honest gate names — each conclusion must come from a real CI step (plan P0.9).
REQUIRED_GATES = (
    "api_pytest_suite",
    "financial_golden_master",
    "point_in_time",
    "no_trading_guards",
    "web_typecheck",
    "desktop_build",
)

# Dependency lock files hashed for reproducibility (path relative to PROJECT_ROOT).
LOCK_FILES = (
    "package-lock.json",
    "apps/api/requirements.txt",
    "apps/api/requirements-dev.txt",
    "apps/desktop/src-tauri/Cargo.lock",
)


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


def _tool_version(args: list[str]) -> str | None:
    try:
        out = subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=15)
        return out.strip().splitlines()[0] if out.strip() else None
    except Exception:  # noqa: BLE001 — evidence capture must not crash the build
        return None


def build_environment() -> dict[str, object]:
    """Capture OS/arch/toolchain versions (plan P0.9 build-env evidence)."""
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "arch": platform.machine(),
        "python_version": platform.python_version(),
        "toolchain": {
            "rustc": _tool_version(["rustc", "--version"]),
            "cargo": _tool_version(["cargo", "--version"]),
            "node": _tool_version(["node", "--version"]),
            "npm": _tool_version(["npm", "--version"]),
        },
    }


def dependency_lock_hashes() -> dict[str, str | None]:
    """sha256 of each dependency lock file for reproducible-build evidence (P0.9)."""
    hashes: dict[str, str | None] = {}
    for rel in LOCK_FILES:
        hashes[rel] = _file_sha256(PROJECT_ROOT / rel)
    return hashes


def installer_artifacts(paths: list[str] | None) -> list[dict[str, object]]:
    """sha256 + size for each built installer (DMG/NSIS/AppImage/DEB) — P0.9."""
    artifacts: list[dict[str, object]] = []
    for raw in paths or []:
        path = Path(raw)
        artifacts.append(
            {
                "name": path.name,
                "sha256": _file_sha256(path),
                "size_bytes": path.stat().st_size if path.is_file() else None,
                "present": path.is_file(),
            }
        )
    return artifacts


def _load_json_arg(value: str | None) -> dict[str, object] | None:
    """Accept either an inline JSON string or a path to a JSON file."""
    if not value:
        return None
    candidate = Path(value)
    text = candidate.read_text(encoding="utf-8") if candidate.is_file() else value
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def gate_conclusions(raw: dict[str, object] | None) -> dict[str, object]:
    """Normalize per-gate conclusions and compute an honest all-pass flag."""
    supplied = {str(k): str(v) for k, v in (raw or {}).items()}
    conclusions = {gate: supplied.get(gate, "missing") for gate in REQUIRED_GATES}
    all_passed = all(conclusions[gate] == "success" for gate in REQUIRED_GATES)
    return {"conclusions": conclusions, "all_required_passed": all_passed}


def certification_status(
    *,
    code_sha: str,
    pytest_report_sha256: str | None,
    golden_fixture_sha256: str | None,
    container_digest: str | None,
    mode: str = "ci_evidence",
) -> dict[str, object]:
    blockers: list[str] = []
    if not code_sha or code_sha == "unknown":
        blockers.append("code_sha_unknown")
    if not pytest_report_sha256:
        blockers.append("pytest_report_digest_missing")
    if not golden_fixture_sha256:
        blockers.append("golden_fixture_digest_missing")
    if mode == "production_release":
        if not container_digest or container_digest == "placeholder":
            blockers.append("container_digest_placeholder")
    elif not container_digest or container_digest == "placeholder":
        blockers.append("container_digest_placeholder")
    return {
        "mode": mode,
        "certified": not blockers if mode == "production_release" else False,
        "evidence_complete": not [b for b in blockers if b != "container_digest_placeholder"]
        if mode == "ci_evidence"
        else not blockers,
        "blockers": blockers,
    }


def build_manifest(
    *,
    pytest_report: Path | None = None,
    golden_hash_file: Path | None = None,
    container_digest: str | None = None,
    mode: str = "ci_evidence",
    gates: dict[str, object] | None = None,
    installers: list[str] | None = None,
    signing: dict[str, object] | None = None,
    notarization: dict[str, object] | None = None,
) -> dict[str, object]:
    approvals = _methodology_approvals()
    code_sha = _git_sha()
    pytest_digest = _file_sha256(pytest_report) if pytest_report else None
    golden_digest = _file_sha256(golden_hash_file) if golden_hash_file else None
    resolved_container = container_digest or os.environ.get("CONTAINER_DIGEST") or "placeholder"
    cert = certification_status(
        code_sha=code_sha,
        pytest_report_sha256=pytest_digest,
        golden_fixture_sha256=golden_digest,
        container_digest=resolved_container,
        mode=mode,
    )
    branch = (
        os.environ.get("GITHUB_REF_NAME", "").strip()
        or os.environ.get("GITHUB_HEAD_REF", "").strip()
        or "unknown"
    )
    workflow_run_id = os.environ.get("GITHUB_RUN_ID", "").strip() or None
    workflow_event = os.environ.get("GITHUB_EVENT_NAME", "").strip() or None
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "code_sha": code_sha,
        "commit_sha": code_sha,
        "branch": branch,
        "workflow_run_id": workflow_run_id,
        "workflow_event": workflow_event,
        "certification_mode": mode,
        "tests_verified": bool(cert.get("evidence_complete")),
        "alembic_head": _alembic_head(),
        "app_version": "0.1.0",
        "environment": os.environ.get("ENVIRONMENT", "ci"),
        "methodology_registry_digest": _methodology_digest(approvals),
        "methodology_approvals": approvals,
        "pytest_report_sha256": pytest_digest,
        "golden_fixture_sha256": golden_digest,
        "container_digest": resolved_container,
        "gate_conclusions": gate_conclusions(gates),
        "build_environment": build_environment(),
        "dependency_lock_hashes": dependency_lock_hashes(),
        "installer_artifacts": installer_artifacts(installers),
        "signing": signing or {"status": "not_captured"},
        "notarization": notarization or {"status": "not_captured"},
        "certification": cert,
        "approval_status": {
            "all_experimental_or_approved": all(
                str(item.get("approval_status") or "")
                in {"experimental", "approved", "approved_for_personal_use"}
                for item in approvals
            ),
            "approved_count": sum(
                1
                for item in approvals
                if item.get("approval_status") in {"approved", "approved_for_personal_use"}
            ),
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
        "--gate-conclusions",
        type=str,
        default=None,
        help="Inline JSON or path mapping required gate names to CI conclusions "
        '(e.g. \'{"api_pytest_suite":"success",...}\').',
    )
    parser.add_argument(
        "--installer",
        action="append",
        default=None,
        help="Path to a built installer to hash (repeatable: DMG/NSIS/AppImage/DEB).",
    )
    parser.add_argument("--signing", type=str, default=None, help="Inline JSON or path: signing evidence.")
    parser.add_argument(
        "--notarization", type=str, default=None, help="Inline JSON or path: notarization evidence."
    )
    parser.add_argument(
        "--mode",
        choices=("ci_evidence", "production_release"),
        default="ci_evidence",
        help="ci_evidence writes digests without claiming production certification; "
        "production_release requires a real container digest.",
    )
    parser.add_argument(
        "--require-certified",
        action="store_true",
        help="Exit non-zero unless mode requirements are satisfied.",
    )
    args = parser.parse_args()

    manifest = build_manifest(
        pytest_report=args.pytest_report,
        golden_hash_file=args.golden_hash_file,
        container_digest=args.container_digest,
        mode=args.mode,
        gates=_load_json_arg(args.gate_conclusions),
        installers=args.installer,
        signing=_load_json_arg(args.signing),
        notarization=_load_json_arg(args.notarization),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}")

    if args.require_certified:
        cert = manifest["certification"]  # type: ignore[index]
        if args.mode == "production_release":
            if not cert.get("certified"):
                print(f"Production release not certifiable: {cert.get('blockers')}", file=sys.stderr)
                return 1
        elif not cert.get("evidence_complete"):
            print(f"CI evidence incomplete: {cert.get('blockers')}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
