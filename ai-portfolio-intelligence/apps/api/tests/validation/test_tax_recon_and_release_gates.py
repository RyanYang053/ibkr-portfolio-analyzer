"""Tax reconciliation service and golden promote CLI smoke tests."""

from __future__ import annotations

from datetime import date


def test_run_tax_reconciliation_persists(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PORTFOLIO_DATA_DIR", str(tmp_path))
    from app.core.config import settings

    monkeypatch.setattr(settings, "persistence_backend", "json")

    from app.db.tax_lot_snapshot_repo import replace_tax_lot_snapshots
    from app.services.tax.reconciliation_service import run_tax_reconciliation

    replace_tax_lot_snapshots(
        account_id="ACC-TAX",
        as_of_date=date.today(),
        lots=[
            {
                "symbol": "AAPL",
                "con_id": 1,
                "quantity": 10,
                "cost_basis_per_share": 100.0,
                "acquired_date": "2020-01-01",
                "currency": "USD",
                "jurisdiction": "US",
                "lot_method": "fifo",
                "source": "test",
                "payload": {},
            }
        ],
    )
    result = run_tax_reconciliation(account_id="ACC-TAX", tax_year=date.today().year, transactions=[1, 2])
    assert result["ok"] is True
    assert result["order_generated"] is False
    assert result["run"]["account_id"] == "ACC-TAX"


def test_run_golden_fixtures_script(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PORTFOLIO_DATA_DIR", str(tmp_path))
    from app.core.config import settings

    monkeypatch.setattr(settings, "persistence_backend", "json")

    from scripts.run_golden_fixtures import main
    import sys

    digest = tmp_path / "golden.sha256"
    argv = ["run_golden_fixtures.py", "--digest-out", str(digest), "--json-out", str(tmp_path / "out.json")]
    monkeypatch.setattr(sys, "argv", argv)
    assert main() == 0
    assert digest.exists()
    assert digest.read_text().strip()


def test_release_manifest_requires_distinct_gates() -> None:
    from scripts.write_decision_os_release_manifest import REQUIRED_JOBS, compute_tests_verified

    assert "financial_golden_master" in REQUIRED_JOBS
    assert "api_pytest_suite" in REQUIRED_JOBS
    partial = {job: "success" for job in REQUIRED_JOBS}
    assert compute_tests_verified(partial) is True
    partial["financial_golden_master"] = "failure"
    assert compute_tests_verified(partial) is False


def test_release_manifest_carries_p0_9_evidence_fields(monkeypatch) -> None:
    """P0.9: the manifest must carry build env, lock hashes, gate conclusions, and
    installer/signing/notarization evidence."""
    monkeypatch.setenv("GIT_SHA", "deadbeefcafe")
    from scripts.write_release_manifest import REQUIRED_GATES, build_manifest

    gates = {gate: "success" for gate in REQUIRED_GATES}
    manifest = build_manifest(gates=gates, signing={"identity": "Test", "verified": True})

    assert manifest["commit_sha"] == "deadbeefcafe"
    assert manifest["gate_conclusions"]["all_required_passed"] is True

    env = manifest["build_environment"]
    assert env["os"] and env["arch"] and env["python_version"]
    assert "toolchain" in env

    locks = manifest["dependency_lock_hashes"]
    # package-lock.json and Cargo.lock exist in the repo, so their hashes must be present.
    assert locks["package-lock.json"]
    assert locks["apps/desktop/src-tauri/Cargo.lock"]

    assert manifest["signing"] == {"identity": "Test", "verified": True}
    assert manifest["notarization"]["status"] == "not_captured"
    assert isinstance(manifest["installer_artifacts"], list)


def test_release_manifest_gate_conclusions_flag_missing() -> None:
    from scripts.write_release_manifest import build_manifest

    manifest = build_manifest(gates={"api_pytest_suite": "success"})
    conclusions = manifest["gate_conclusions"]["conclusions"]
    assert conclusions["api_pytest_suite"] == "success"
    assert conclusions["no_trading_guards"] == "missing"
    assert manifest["gate_conclusions"]["all_required_passed"] is False
