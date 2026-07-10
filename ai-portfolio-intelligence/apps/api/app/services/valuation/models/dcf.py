from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.services.valuation.models.base import ValuationInputLineage, ValuationOutput, ValuationScenario
from app.services.valuation.models.validation import positive_decimal, require_wacc_above_terminal_growth


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


def evaluate_dcf(inputs: DcfInputs, scenarios: list[ValuationScenario]) -> ValuationOutput:
    exclusions: list[str] = ["general_operating_valuation_model_not_validated"]
    lineage = ValuationInputLineage(
        source_ids=inputs.source_ids,
        as_of=inputs.as_of,
        currency=inputs.currency,
        share_count_source="diluted_share_count",
    )

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

    return _withheld(lineage, exclusions)
