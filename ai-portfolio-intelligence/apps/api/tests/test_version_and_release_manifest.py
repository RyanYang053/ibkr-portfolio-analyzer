from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.domain import AccountSummary, utc_now
from app.services.data_quality.validation import prepare_professional_response
from app.services.tax.canadian_acb import build_canadian_acb_report
from scripts.write_release_manifest import build_manifest
from tests.test_tax_modules import _txn


client = TestClient(app)


def test_version_endpoint_exposes_release_fields(monkeypatch):
    monkeypatch.setenv("GIT_SHA", "abc123deadbeef")
    response = client.get("/version")
    assert response.status_code == 200
    payload = response.json()
    assert payload["git_sha"] == "abc123deadbeef"
    assert payload["app_version"] == "0.1.0"
    assert "alembic_head" in payload
    assert payload["environment"]
    assert len(payload["methodology_registry_digest"]) == 64


def test_release_manifest_writer_includes_sha_and_approvals(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("GIT_SHA", "manifest-sha-001")
    monkeypatch.setenv("ENVIRONMENT", "ci")
    out = tmp_path / "release-manifest.json"
    pytest_report = tmp_path / "pytest.xml"
    pytest_report.write_text("<testsuite/>", encoding="utf-8")
    golden = tmp_path / "golden.txt"
    golden.write_text("abc", encoding="utf-8")
    from scripts.write_release_manifest import build_manifest

    manifest = build_manifest(pytest_report=pytest_report, golden_hash_file=golden)
    out.write_text(json.dumps(manifest), encoding="utf-8")
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["code_sha"] == "manifest-sha-001"
    assert loaded["alembic_head"]
    assert loaded["methodology_registry_digest"]
    assert loaded["container_digest"] == "placeholder"
    assert loaded["pytest_report_sha256"]
    assert loaded["golden_fixture_sha256"]
    assert "methodology_approvals" in loaded
    assert "approval_status" in loaded
    assert loaded["certification"]["certified"] is False
    assert "container_digest_placeholder" in loaded["certification"]["blockers"]


def test_release_manifest_require_certified_rejects_unknown_sha(monkeypatch, tmp_path: Path, capsys):
    monkeypatch.delenv("GIT_SHA", raising=False)
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    from scripts import write_release_manifest as wrm

    monkeypatch.setattr(wrm, "_git_sha", lambda: "unknown")
    pytest_report = tmp_path / "pytest.xml"
    pytest_report.write_text("<testsuite/>", encoding="utf-8")
    golden = tmp_path / "golden.txt"
    golden.write_text("abc", encoding="utf-8")
    out = tmp_path / "release-manifest.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "write_release_manifest.py",
            "--out",
            str(out),
            "--pytest-report",
            str(pytest_report),
            "--golden-hash-file",
            str(golden),
            "--require-certified",
        ],
    )
    assert wrm.main() == 1


def test_ca_affiliated_missing_fail_closes_filing_ready():
    report = build_canadian_acb_report(
        "MOCK-001",
        [
            _txn(
                account_id="MOCK-001",
                symbol="RY",
                trade_date=date(2024, 1, 1),
                action="buy",
                quantity=100,
                price=100,
                commission=0,
                currency="CAD",
            )
        ],
        affiliated_accounts=None,
        affiliated_transactions=None,
    )
    assert report.methodology_status == "provisional_affiliated_data_required"
    assert report.data_quality["affiliated_data_detail"] == "provisional_no_affiliated_accounts"

    summary = AccountSummary(
        account_id="MOCK-001",
        net_liquidation=10000,
        cash=1000,
        buying_power=1000,
        margin_requirement=0.0,
        excess_liquidity=0.0,
        total_unrealized_pnl=0.0,
        total_realized_pnl=0.0,
        base_currency="CAD",
        data_timestamp=utc_now(),
    )
    payload = prepare_professional_response(
        {
            "account_id": report.account_id,
            "jurisdiction": report.jurisdiction,
            "methodology_status": report.methodology_status,
            "data_quality": report.data_quality,
        },
        summary,
        [],
        {"status": "ok", "metrics": {"missing_price_count": 0}},
        methodology_id="tax_lot_methodology",
    )
    assert payload["tax_output_provisional"] is True
    assert payload["professional_language_allowed"] is False
    assert payload["filing_ready"] is False


def test_ca_affiliated_ids_without_transactions_fail_closes():
    report = build_canadian_acb_report(
        "MOCK-001",
        [
            _txn(
                account_id="MOCK-001",
                symbol="RY",
                trade_date=date(2024, 1, 1),
                action="buy",
                quantity=100,
                price=100,
                commission=0,
                currency="CAD",
            )
        ],
        affiliated_accounts=["MOCK-002"],
        affiliated_transactions=[],
    )
    assert report.methodology_status == "provisional_affiliated_data_required"
    assert (
        report.data_quality["affiliated_data_detail"]
        == "provisional_affiliated_accounts_missing_transactions"
    )
