from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.services.methodology_registry import MethodologyRecord
from app.services.valuation.models.base import ValuationScenario
from app.services.valuation.models.dcf import DcfInputs, evaluate_dcf

STABLE_DCF = DcfInputs(
    ttm_revenue=Decimal("1000000000"),
    operating_margin=Decimal("0.20"),
    tax_rate=Decimal("0.21"),
    depreciation_amortization=Decimal("50000000"),
    capex=Decimal("40000000"),
    working_capital_change=Decimal("10000000"),
    net_debt=Decimal("200000000"),
    diluted_share_count=Decimal("100000000"),
    wacc=Decimal("0.10"),
    terminal_growth=Decimal("0.03"),
    currency="USD",
    as_of=date(2025, 12, 31),
    source_ids=["golden_fixture"],
)

SCENARIOS = [
    ValuationScenario(name="base", assumptions={"revenue_growth": Decimal("0.05"), "terminal_growth": Decimal("0.03")}),
    ValuationScenario(name="bull", assumptions={"revenue_growth": Decimal("0.08"), "terminal_growth": Decimal("0.04")}),
    ValuationScenario(name="bear", assumptions={"revenue_growth": Decimal("0.02"), "terminal_growth": Decimal("0.02")}),
]

GOLDEN_BASE_PER_SHARE = 23.31


def test_dcf_golden_fixture_within_tolerance(monkeypatch):
    approved = MethodologyRecord(
        methodology_id="general_operating_dcf",
        name="General Operating DCF",
        version="1.0.0",
        effective_date=date(2026, 7, 1),
        owner="valuation",
        approval_status="approved",
        independent_validation_fixture="tests/test_valuation_golden_fixtures.py",
        known_limitations=tuple(),
        rollback_version=None,
    )
    monkeypatch.setattr("app.services.valuation.models.dcf.require_methodology_status", lambda *_args, **_kwargs: approved)
    output = evaluate_dcf(STABLE_DCF, SCENARIOS)
    assert output.status == "available"
    base = next(item for item in output.scenarios if item.name == "base")
    assert float(base.per_share_value) == pytest.approx(GOLDEN_BASE_PER_SHARE, rel=0.02)


def test_dcf_withheld_without_methodology_approval():
    output = evaluate_dcf(STABLE_DCF, SCENARIOS)
    assert output.status == "withheld"
    assert "general_operating_valuation_model_not_validated" in output.exclusions


def test_dcf_rejects_invalid_wacc_terminal_spread():
    invalid = DcfInputs(
        **{
            **STABLE_DCF.__dict__,
            "wacc": Decimal("0.02"),
            "terminal_growth": Decimal("0.03"),
        }
    )
    output = evaluate_dcf(invalid, SCENARIOS)
    assert "wacc_must_exceed_terminal_growth" in output.exclusions
