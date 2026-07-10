from app.services.methodology_registry import DEFAULT_METHODOLOGIES, list_methodologies
from app.services.model_governance import can_promote_to_production, coverage_summary_for_page


def test_methodology_registry_lists_versioned_records():
    records = list_methodologies()
    assert len(records) >= 3
    ids = {record["methodology_id"] for record in records}
    assert "portfolio_pnl_reconciliation" in ids
    assert "scenario_fair_value" in ids


def test_withheld_models_cannot_promote_to_production():
    withheld = next(record for record in DEFAULT_METHODOLOGIES if record.approval_status == "withheld")
    allowed, blockers = can_promote_to_production(withheld)
    assert allowed is False
    assert blockers


def test_coverage_summary_flags_missing_items():
    summary = coverage_summary_for_page(
        {
            "historical_metrics": "sufficient",
            "benchmark_returns": "missing",
        },
        exclusions=["IONQ"],
    )
    assert summary["status"] == "partial"
    assert "benchmark_returns" in summary["missing_items"]
    assert summary["exclusions"] == ["IONQ"]
