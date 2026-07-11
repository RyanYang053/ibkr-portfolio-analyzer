from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.services.model_governance import MethodologyNotApproved, require_methodology_status
from app.services.valuation.models.base import ScenarioValuation, ValuationInputLineage, ValuationOutput, ValuationScenario
from app.services.valuation.models.validation import positive_decimal

METHODOLOGY_ID = "utility_rate_base"
CODE_SHA = hashlib.sha256(b"utility_rate_base_v1").hexdigest()


@dataclass(frozen=True)
class UtilityRateBaseInputs:
    rate_base: Decimal | None
    allowed_roe: Decimal | None
    equity_capitalization: Decimal | None
    regulatory_lag_years: Decimal | None
    capex: Decimal | None
    debt_financing: Decimal | None
    debt_cost: Decimal | None
    payout_ratio: Decimal | None
    share_count: Decimal | None
    currency: str
    as_of: date
    source_ids: list[str]


def evaluate_utility_rate_base(
    inputs: UtilityRateBaseInputs,
    scenarios: list[ValuationScenario],
) -> ValuationOutput:
    exclusions: list[str] = []
    lineage = ValuationInputLineage(
        source_ids=inputs.source_ids,
        as_of=inputs.as_of,
        currency=inputs.currency,
        share_count_source="share_count",
        field_lineage={
            "rate_base": inputs.source_ids,
            "allowed_roe": inputs.source_ids,
            "equity_capitalization": inputs.source_ids,
        },
        methodology_id=METHODOLOGY_ID,
        methodology_version="1.0.0",
        code_sha=CODE_SHA,
    )

    positive_decimal(inputs.rate_base, "rate_base", exclusions)
    positive_decimal(inputs.allowed_roe, "allowed_roe", exclusions)
    positive_decimal(inputs.equity_capitalization, "equity_capitalization", exclusions)
    positive_decimal(inputs.capex, "capex", exclusions)
    if inputs.debt_financing is None:
        exclusions.append("debt_financing_unavailable")
    positive_decimal(inputs.share_count, "share_count", exclusions)
    if len(scenarios) < 3:
        exclusions.append("base_bull_bear_scenarios_required")
    if exclusions:
        return ValuationOutput(
            status="withheld",
            enterprise_value=None,
            equity_value=None,
            per_share_value=None,
            scenarios=[],
            exclusions=exclusions,
            lineage=lineage,
        )

    try:
        require_methodology_status(METHODOLOGY_ID)
    except MethodologyNotApproved:
        exclusions.append("utility_valuation_model_not_validated")
        return ValuationOutput(
            status="withheld",
            enterprise_value=None,
            equity_value=None,
            per_share_value=None,
            scenarios=[],
            exclusions=exclusions,
            lineage=lineage,
        )

    scenario_outputs: list[ScenarioValuation] = []
    for scenario in scenarios:
        allowed_roe = scenario.assumptions.get("allowed_roe", inputs.allowed_roe or Decimal("0"))
        equity_cap = scenario.assumptions.get("equity_capitalization", inputs.equity_capitalization or Decimal("0"))
        rate_base = inputs.rate_base or Decimal("0")
        equity_earnings = rate_base * allowed_roe * equity_cap
        payout = scenario.assumptions.get("payout_ratio", inputs.payout_ratio or Decimal("0.6"))
        retained = equity_earnings * (Decimal("1") - payout)
        lag = inputs.regulatory_lag_years or Decimal("0")
        equity_value = rate_base * equity_cap + retained * (Decimal("1") - lag)
        shares = inputs.share_count or Decimal("0")
        per_share = equity_value / shares if shares > 0 else Decimal("0")
        scenario_outputs.append(
            ScenarioValuation(
                name=scenario.name,
                per_share_value=per_share,
                enterprise_value=equity_value,
                equity_value=equity_value,
                assumptions={"allowed_roe": allowed_roe, "equity_capitalization": equity_cap, "payout_ratio": payout},
            )
        )

    base = next(item for item in scenario_outputs if item.name == "base")
    return ValuationOutput(
        status="available",
        enterprise_value=base.enterprise_value,
        equity_value=base.equity_value,
        per_share_value=base.per_share_value,
        scenarios=scenario_outputs,
        exclusions=[],
        lineage=lineage,
    )
