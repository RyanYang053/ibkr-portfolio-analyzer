from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from app.db.methodology_version_repo import MethodologyVersion


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
        approval_status="experimental",
        independent_validation_fixture="tests/test_financial_integrity.py",
        known_limitations=("Requires complete cash-flow ledger for exact reconciliation.",),
        rollback_version=None,
    ),
    MethodologyRecord(
        methodology_id="return_engine",
        name="Return Engine",
        version="0.1.0",
        effective_date=date(2026, 7, 10),
        owner="portfolio-accounting",
        approval_status="experimental",
        independent_validation_fixture="tests/test_return_engine.py",
        known_limitations=("Exact TWR requires bracketed NAV around every external flow.",),
        rollback_version=None,
    ),
    MethodologyRecord(
        methodology_id="performance_attribution",
        name="Performance Attribution",
        version="0.1.0",
        effective_date=date(2026, 7, 10),
        owner="portfolio-analytics",
        approval_status="experimental",
        independent_validation_fixture="tests/test_attribution_linking.py",
        known_limitations=("Requires licensed benchmark constituent data for production attribution.",),
        rollback_version=None,
    ),
    MethodologyRecord(
        methodology_id="tax_lot_methodology",
        name="Tax Lot Methodology",
        version="0.1.0",
        effective_date=date(2026, 7, 10),
        owner="tax-analytics",
        approval_status="experimental",
        independent_validation_fixture="tests/test_tax_lot_transition.py",
        known_limitations=("Tax output is decision support until reconciled to broker tax forms.",),
        rollback_version=None,
    ),
    MethodologyRecord(
        methodology_id="options_strategy_engine",
        name="Options Strategy Engine",
        version="0.1.0",
        effective_date=date(2026, 7, 10),
        owner="derivatives-analytics",
        approval_status="experimental",
        independent_validation_fixture="tests/test_options_provider_provenance.py",
        known_limitations=("Live options require production liquidity gates.",),
        rollback_version=None,
    ),
    MethodologyRecord(
        methodology_id="derivative_stress",
        name="Derivative Stress",
        version="0.1.0",
        effective_date=date(2026, 7, 10),
        owner="risk-analytics",
        approval_status="experimental",
        independent_validation_fixture="tests/test_option_portfolio_greeks.py",
        known_limitations=("Scenario repricing requires contract master and market inputs.",),
        rollback_version=None,
    ),
    MethodologyRecord(
        methodology_id="fundamental_metric_derivation",
        name="Fundamental Metric Derivation",
        version="0.1.0",
        effective_date=date(2026, 7, 10),
        owner="fundamentals",
        approval_status="experimental",
        independent_validation_fixture="tests/test_fundamental_field_lineage.py",
        known_limitations=("Rolling TTM requires four consecutive standalone quarters.",),
        rollback_version=None,
    ),
    MethodologyRecord(
        methodology_id="general_operating_dcf",
        name="General Operating DCF",
        version="0.0.0",
        effective_date=date(2026, 7, 10),
        owner="valuation",
        approval_status="withheld",
        independent_validation_fixture="tests/test_valuation_model_gates.py",
        known_limitations=("Withheld until independent golden fixture passes.",),
        rollback_version=None,
    ),
    MethodologyRecord(
        methodology_id="bank_residual_income",
        name="Bank Residual Income",
        version="0.0.0",
        effective_date=date(2026, 7, 10),
        owner="valuation",
        approval_status="withheld",
        independent_validation_fixture="tests/test_valuation_model_gates.py",
        known_limitations=("Withheld until independent golden fixture passes.",),
        rollback_version=None,
    ),
    MethodologyRecord(
        methodology_id="reit_nav_affo",
        name="REIT NAV AFFO",
        version="0.0.0",
        effective_date=date(2026, 7, 10),
        owner="valuation",
        approval_status="withheld",
        independent_validation_fixture="tests/test_valuation_model_gates.py",
        known_limitations=("Withheld until independent golden fixture passes.",),
        rollback_version=None,
    ),
    MethodologyRecord(
        methodology_id="utility_rate_base",
        name="Utility Rate Base",
        version="0.0.0",
        effective_date=date(2026, 7, 10),
        owner="valuation",
        approval_status="withheld",
        independent_validation_fixture="tests/test_valuation_model_gates.py",
        known_limitations=("Withheld until independent golden fixture passes.",),
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
        version="1.2.0",
        effective_date=date(2026, 7, 10),
        owner="portfolio-construction",
        approval_status="experimental",
        independent_validation_fixture="tests/test_optimizer_reference_solutions.py",
        known_limitations=(
            "Full-portfolio turnover constraints; production proposals remain experimental.",
        ),
        rollback_version="1.1.0",
    ),
    MethodologyRecord(
        methodology_id="investor_lens_buffett_quality",
        name="Quality and Leverage Heuristic",
        version="0.2.0",
        effective_date=date(2026, 7, 15),
        owner="decision-center",
        approval_status="experimental",
        independent_validation_fixture="tests/test_investor_lenses.py",
        known_limitations=(
            "Deterministic heuristic with ROIC/owner-earnings proxies; not full Buffett methodology "
            "(moat, capital allocation, valuation range still not implemented).",
        ),
        rollback_version="0.1.0",
    ),
    MethodologyRecord(
        methodology_id="investor_lens_graham_piotroski",
        name="Investor Lens Graham Piotroski",
        version="0.1.0",
        effective_date=date(2026, 7, 15),
        owner="decision-center",
        approval_status="experimental",
        independent_validation_fixture="tests/test_investor_lenses.py",
        known_limitations=("Binary fundamental flags; incomplete fundamentals → provisional.",),
        rollback_version=None,
    ),
    MethodologyRecord(
        methodology_id="investor_lens_greenblatt",
        name="Investor Lens Greenblatt",
        version="0.1.0",
        effective_date=date(2026, 7, 15),
        owner="decision-center",
        approval_status="experimental",
        independent_validation_fixture="tests/test_investor_lenses.py",
        known_limitations=("Earnings-yield proxy via forward PE; experimental.",),
        rollback_version=None,
    ),
    MethodologyRecord(
        methodology_id="investor_lens_lynch_garp",
        name="Investor Lens Lynch GARP",
        version="0.1.0",
        effective_date=date(2026, 7, 15),
        owner="decision-center",
        approval_status="experimental",
        independent_validation_fixture="tests/test_investor_lenses.py",
        known_limitations=("PEG proxy only; growth units may be ratio or percent.",),
        rollback_version=None,
    ),
    MethodologyRecord(
        methodology_id="investor_lens_marks_risk",
        name="Investor Lens Marks Risk",
        version="0.1.0",
        effective_date=date(2026, 7, 15),
        owner="decision-center",
        approval_status="experimental",
        independent_validation_fixture="tests/test_investor_lenses.py",
        known_limitations=("Uses portfolio risk metrics when holding-level risk absent.",),
        rollback_version=None,
    ),
    MethodologyRecord(
        methodology_id="investor_lens_regime_balance",
        name="Investor Lens Regime Balance",
        version="0.1.0",
        effective_date=date(2026, 7, 15),
        owner="decision-center",
        approval_status="experimental",
        independent_validation_fixture="tests/test_investor_lenses.py",
        known_limitations=("ETF-proxy factor exposures only.",),
        rollback_version=None,
    ),
    MethodologyRecord(
        methodology_id="investor_lens_factor_quality",
        name="Investor Lens Factor Quality",
        version="0.1.0",
        effective_date=date(2026, 7, 15),
        owner="decision-center",
        approval_status="experimental",
        independent_validation_fixture="tests/test_investor_lenses.py",
        known_limitations=("Combines factor proxy with fundamentals; experimental.",),
        rollback_version=None,
    ),
    MethodologyRecord(
        methodology_id="investor_lens_bogle_discipline",
        name="Investor Lens Bogle Discipline",
        version="0.1.0",
        effective_date=date(2026, 7, 15),
        owner="decision-center",
        approval_status="experimental",
        independent_validation_fixture="tests/test_investor_lenses.py",
        known_limitations=("Concentration and turnover heuristics only.",),
        rollback_version=None,
    ),
    MethodologyRecord(
        methodology_id="investor_lens_munger_inversion",
        name="Investor Lens Munger Inversion",
        version="0.1.0",
        effective_date=date(2026, 7, 15),
        owner="decision-center",
        approval_status="experimental",
        independent_validation_fixture="tests/test_investor_lenses.py",
        known_limitations=("Failure-mode checklist; not a valuation.",),
        rollback_version=None,
    ),
    MethodologyRecord(
        methodology_id="decision_center_holding",
        name="Decision Center Holding Gates",
        version="0.1.0",
        effective_date=date(2026, 7, 15),
        owner="decision-center",
        approval_status="experimental",
        independent_validation_fixture="tests/test_decision_center.py",
        known_limitations=(
            "Ordered deterministic gates; LLM may summarize only and must not compute lens scores.",
            "Valuation remains withheld unless methodology-approved.",
        ),
        rollback_version=None,
    ),
)


def _record_to_version(record: MethodologyRecord) -> MethodologyVersion:
    effective = datetime.combine(record.effective_date, datetime.min.time(), tzinfo=timezone.utc)
    return MethodologyVersion(
        methodology_id=record.methodology_id,
        name=record.name,
        version=record.version,
        effective_at=effective,
        status=record.approval_status,
        owner=record.owner,
        code_sha=None,
        artifact_sha256=None,
        known_limitations=record.known_limitations,
        rollback_version=record.rollback_version,
        independent_validation_fixture=record.independent_validation_fixture,
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


def default_methodology_versions() -> list[MethodologyVersion]:
    return [_record_to_version(record) for record in DEFAULT_METHODOLOGIES]
