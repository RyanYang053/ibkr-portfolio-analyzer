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
