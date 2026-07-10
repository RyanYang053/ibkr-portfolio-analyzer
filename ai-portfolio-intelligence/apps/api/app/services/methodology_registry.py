from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class MethodologyRecord:
    methodology_id: str
    name: str
    version: str
    effective_date: date
    owner: str
    approval_status: str
    independent_validation_fixture: str | None
    known_limitations: tuple[str, ...]
    rollback_version: str | None


DEFAULT_METHODOLOGIES: tuple[MethodologyRecord, ...] = (
    MethodologyRecord(
        methodology_id="portfolio_pnl_reconciliation",
        name="Portfolio PnL Reconciliation",
        version="1.0.0",
        effective_date=date(2026, 7, 1),
        owner="portfolio-accounting",
        approval_status="approved",
        independent_validation_fixture="tests/test_financial_integrity.py",
        known_limitations=("Requires complete cash-flow ledger for exact reconciliation.",),
        rollback_version=None,
    ),
    MethodologyRecord(
        methodology_id="factor_exposure_regression",
        name="ETF Proxy Factor Exposure Regression",
        version="0.2.0",
        effective_date=date(2026, 7, 10),
        owner="risk-analytics",
        approval_status="experimental",
        independent_validation_fixture="tests/test_risk_factor_diagnostics.py",
        known_limitations=(
            "Uses ETF factor proxies, not fundamental factor models.",
            "HAC inference requires sufficient aligned return history.",
        ),
        rollback_version="0.1.0",
    ),
    MethodologyRecord(
        methodology_id="scenario_fair_value",
        name="Scenario Fair Value",
        version="0.0.0",
        effective_date=date(2026, 7, 10),
        owner="valuation",
        approval_status="withheld",
        independent_validation_fixture="tests/test_valuation_model_gates.py",
        known_limitations=("Fair values are withheld until validated valuation models pass release gates.",),
        rollback_version=None,
    ),
    MethodologyRecord(
        methodology_id="portfolio_optimizer",
        name="Constrained Portfolio Optimizer",
        version="1.1.0",
        effective_date=date(2026, 7, 8),
        owner="portfolio-construction",
        approval_status="experimental",
        independent_validation_fixture="tests/test_optimizer_reference_solutions.py",
        known_limitations=("Live advanced optimization remains unavailable until infeasibility gates pass in production.",),
        rollback_version="1.0.0",
    ),
)


def list_methodologies() -> list[dict[str, object]]:
    from app.db.methodology_repo import load_methodology_registry

    records = load_methodology_registry()
    return [
        {
            "methodology_id": record.methodology_id,
            "name": record.name,
            "version": record.version,
            "effective_date": record.effective_date.isoformat(),
            "owner": record.owner,
            "approval_status": record.approval_status,
            "independent_validation_fixture": record.independent_validation_fixture,
            "known_limitations": list(record.known_limitations),
            "rollback_version": record.rollback_version,
        }
        for record in records
    ]
