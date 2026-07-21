"""Release manifest writer — tests_verified from required gate conclusions."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


# Honest gate names — each must be supplied from a real CI step conclusion.
REQUIRED_JOBS = (
    "api_pytest_suite",
    "financial_golden_master",
    "point_in_time",
    "no_trading_guards",
    "web_typecheck",
    "desktop_build",
)


def compute_tests_verified(required_jobs: dict[str, str]) -> bool:
    """True only when every required gate conclusion is success."""
    return all(required_jobs.get(job) == "success" for job in REQUIRED_JOBS)


def build_release_manifest(
    *,
    commit_sha: str,
    branch: str,
    workflow_run_id: str,
    required_jobs: dict[str, str],
    methodology_registry_digest: str = "",
    database_schema_revision: str = "",
    sbom_sha256: str = "",
    desktop_artifact_sha256: str = "",
    golden_fixture_sha256: str = "",
) -> dict[str, Any]:
    tests_verified = compute_tests_verified(required_jobs)
    return {
        "commit_sha": commit_sha,
        "branch": branch,
        "workflow_run_id": workflow_run_id,
        "required_jobs": {job: required_jobs.get(job, "missing") for job in REQUIRED_JOBS},
        "tests_verified": tests_verified,
        "methodology_registry_digest": methodology_registry_digest,
        "database_schema_revision": database_schema_revision,
        "sbom_sha256": sbom_sha256,
        "desktop_artifact_sha256": desktop_artifact_sha256,
        "golden_fixture_sha256": golden_fixture_sha256,
    }


def write_release_manifest(path: Path, manifest: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    path.write_text(body, encoding="utf-8")
    return hashlib.sha256(body.encode("utf-8")).hexdigest()
