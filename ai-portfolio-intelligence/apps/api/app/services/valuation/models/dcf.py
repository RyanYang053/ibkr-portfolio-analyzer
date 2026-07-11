from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.services.model_governance import MethodologyNotApproved, require_methodology_status
from app.services.valuation.models.base import (
    ScenarioValuation,
    ValuationInputLineage,
    ValuationOutput,
    ValuationScenario,
)
from app.services.valuation.models.validation import positive_decimal, require_wacc_above_terminal_growth

METHODOLOGY_ID = "general_operating_dcf"
CODE_SHA = hashlib.sha256(b"general_operating_dcf_v1").hexdigest()


@dataclass(frozen=True)
class DcfInputs:
    ttm_revenue: Decimal | None
    operating_margin: Decimal | None
    tax_rate: Decimal | None
    depreciation_amortization: Decimal | None
    capex: Decimal | None
    working_capital_change: Decimal | None
    net_debt: Decimal | None
    diluted_share_count: Decimal | None
    wacc: Decimal
    terminal_growth: Decimal
    currency: str
    as_of: date
    source_ids: list[str]


def _lineage(inputs: DcfInputs, field_lineage: dict[str, list[str]]) -> ValuationInputLineage:
    return ValuationInputLineage(
        source_ids=inputs.source_ids,
        as_of=inputs.as_of,
        currency=inputs.currency,
        share_count_source="diluted_share_count",
        field_lineage=field_lineage,
        methodology_id=METHODOLOGY_ID,
        methodology_version="1.0.0",
        code_sha=CODE_SHA,
    )


def _withheld(lineage: ValuationInputLineage, exclusions: list[str]) -> ValuationOutput:
    return ValuationOutput(
        status="withheld",
        enterprise_value=None,
        equity_value=None,
        per_share_value=None,
        scenarios=[],
        exclusions=exclusions,
        lineage=lineage,
    )


def _scenario_assumption(scenario: ValuationScenario, key: str, default: Decimal) -> Decimal:
    return scenario.assumptions.get(key, default)


def _evaluate_scenario(inputs: DcfInputs, scenario: ValuationScenario) -> ScenarioValuation | None:
    revenue_prior = inputs.ttm_revenue
    if revenue_prior is None:
        return None
    growth = _scenario_assumption(scenario, "revenue_growth", Decimal("0.05"))
    margin = _scenario_assumption(scenario, "operating_margin", inputs.operating_margin or Decimal("0"))
    tax_rate = _scenario_assumption(scenario, "tax_rate", inputs.tax_rate or Decimal("0"))
    wacc = _scenario_assumption(scenario, "wacc", inputs.wacc)
    terminal_growth = _scenario_assumption(scenario, "terminal_growth", inputs.terminal_growth)
    if wacc <= terminal_growth:
        return None

    pv_fcff = Decimal("0")
    revenue_t = revenue_prior
    fcff_5 = Decimal("0")
    for year in range(1, 6):
        revenue_t = revenue_t * (Decimal("1") + growth)
        ebit_t = revenue_t * margin
        nopat_t = ebit_t * (Decimal("1") - tax_rate)
        da_t = inputs.depreciation_amortization or Decimal("0")
        capex_t = inputs.capex or Decimal("0")
        delta_nwc_t = inputs.working_capital_change or Decimal("0")
        fcff_t = nopat_t + da_t - capex_t - delta_nwc_t
        pv_fcff += fcff_t / (Decimal("1") + wacc) ** year
        if year == 5:
            fcff_5 = fcff_t

    terminal = fcff_5 * (Decimal("1") + terminal_growth) / (wacc - terminal_growth)
    enterprise_value = pv_fcff + terminal / (Decimal("1") + wacc) ** 5
    net_debt = inputs.net_debt or Decimal("0")
    equity_value = enterprise_value - net_debt
    shares = inputs.diluted_share_count or Decimal("0")
    if shares <= 0:
        return None
    per_share = equity_value / shares
    return ScenarioValuation(
        name=scenario.name,
        per_share_value=per_share,
        enterprise_value=enterprise_value,
        equity_value=equity_value,
        assumptions={
            "revenue_growth": growth,
            "operating_margin": margin,
            "tax_rate": tax_rate,
            "wacc": wacc,
            "terminal_growth": terminal_growth,
        },
    )


def evaluate_dcf(inputs: DcfInputs, scenarios: list[ValuationScenario]) -> ValuationOutput:
    exclusions: list[str] = []
    field_lineage = {
        "ttm_revenue": inputs.source_ids,
        "operating_margin": inputs.source_ids,
        "net_debt": inputs.source_ids,
        "diluted_share_count": inputs.source_ids,
    }
    lineage = _lineage(inputs, field_lineage)

    positive_decimal(inputs.ttm_revenue, "ttm_revenue", exclusions)
    positive_decimal(inputs.operating_margin, "operating_margin", exclusions)
    positive_decimal(inputs.tax_rate, "tax_rate", exclusions)
    positive_decimal(inputs.depreciation_amortization, "depreciation_amortization", exclusions)
    positive_decimal(inputs.capex, "capex", exclusions)
    if inputs.working_capital_change is None:
        exclusions.append("working_capital_change_unavailable")
    if inputs.net_debt is None:
        exclusions.append("net_debt_unavailable")
    positive_decimal(inputs.diluted_share_count, "diluted_share_count", exclusions)
    require_wacc_above_terminal_growth(inputs.wacc, inputs.terminal_growth, exclusions)
    if len(scenarios) < 3:
        exclusions.append("base_bull_bear_scenarios_required")

    if exclusions:
        return _withheld(lineage, exclusions)

    try:
        require_methodology_status(METHODOLOGY_ID)
    except MethodologyNotApproved:
        exclusions.append("general_operating_valuation_model_not_validated")
        return _withheld(lineage, exclusions)

    scenario_outputs = [_evaluate_scenario(inputs, scenario) for scenario in scenarios]
    if any(item is None for item in scenario_outputs):
        exclusions.append("scenario_inputs_invalid")
        return _withheld(lineage, exclusions)

    base = next(item for item in scenario_outputs if item.name == "base")
    sensitivity_grid = {
        "wacc": {
            "low": (_evaluate_scenario(inputs, ValuationScenario(name="bear", assumptions=scenarios[2].assumptions)) or base).per_share_value,
            "high": (_evaluate_scenario(inputs, ValuationScenario(name="bull", assumptions=scenarios[1].assumptions)) or base).per_share_value,
        }
    }
    return ValuationOutput(
        status="available",
        enterprise_value=base.enterprise_value,
        equity_value=base.equity_value,
        per_share_value=base.per_share_value,
        scenarios=[item for item in scenario_outputs if item is not None],
        exclusions=[],
        lineage=lineage,
        sensitivity_grid=sensitivity_grid,
    )
