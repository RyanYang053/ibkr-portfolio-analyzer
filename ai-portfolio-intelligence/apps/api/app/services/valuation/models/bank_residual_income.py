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
from app.services.valuation.models.validation import positive_decimal

METHODOLOGY_ID = "bank_residual_income"
CODE_SHA = hashlib.sha256(b"bank_residual_income_v1").hexdigest()


@dataclass(frozen=True)
class BankResidualIncomeInputs:
    tangible_common_equity: Decimal | None
    tangible_book_per_share: Decimal | None
    normalized_roe: Decimal | None
    cost_of_equity: Decimal | None
    retention_ratio: Decimal | None
    share_count: Decimal | None
    currency: str
    as_of: date
    source_ids: list[str]
    forecast_horizon: int = 5
    terminal_growth: Decimal = Decimal("0.03")


def evaluate_bank_residual_income(
    inputs: BankResidualIncomeInputs,
    scenarios: list[ValuationScenario],
) -> ValuationOutput:
    exclusions: list[str] = []
    lineage = ValuationInputLineage(
        source_ids=inputs.source_ids,
        as_of=inputs.as_of,
        currency=inputs.currency,
        share_count_source="share_count",
        field_lineage={
            "tangible_book_per_share": inputs.source_ids,
            "normalized_roe": inputs.source_ids,
            "cost_of_equity": inputs.source_ids,
        },
        methodology_id=METHODOLOGY_ID,
        methodology_version="1.0.0",
        code_sha=CODE_SHA,
    )

    positive_decimal(inputs.tangible_book_per_share, "tangible_book_per_share", exclusions)
    positive_decimal(inputs.normalized_roe, "normalized_roe", exclusions)
    positive_decimal(inputs.cost_of_equity, "cost_of_equity", exclusions)
    if inputs.retention_ratio is None:
        exclusions.append("retention_ratio_unavailable")
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
        exclusions.append("bank_valuation_model_not_validated")
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
        rote = scenario.assumptions.get("normalized_roe", inputs.normalized_roe or Decimal("0"))
        coe = scenario.assumptions.get("cost_of_equity", inputs.cost_of_equity or Decimal("0"))
        retention = scenario.assumptions.get("retention_ratio", inputs.retention_ratio or Decimal("0"))
        terminal_growth = scenario.assumptions.get("terminal_growth", inputs.terminal_growth)
        tbv = inputs.tangible_book_per_share or Decimal("0")
        pv_ri = Decimal("0")
        beginning_tbv = tbv
        for _ in range(inputs.forecast_horizon):
            ri_t = (rote - coe) * beginning_tbv
            pv_ri += ri_t / (Decimal("1") + coe)
            beginning_tbv *= Decimal("1") + rote * retention
        terminal_ri = (rote - coe) * beginning_tbv * (Decimal("1") + terminal_growth) / (coe - terminal_growth)
        value_per_share = tbv + pv_ri + terminal_ri / (Decimal("1") + coe) ** inputs.forecast_horizon
        equity_value = value_per_share * (inputs.share_count or Decimal("0"))
        scenario_outputs.append(
            ScenarioValuation(
                name=scenario.name,
                per_share_value=value_per_share,
                enterprise_value=None,
                equity_value=equity_value,
                assumptions={
                    "normalized_roe": rote,
                    "cost_of_equity": coe,
                    "retention_ratio": retention,
                    "terminal_growth": terminal_growth,
                },
            )
        )

    base = next(item for item in scenario_outputs if item.name == "base")
    return ValuationOutput(
        status="available",
        enterprise_value=None,
        equity_value=base.equity_value,
        per_share_value=base.per_share_value,
        scenarios=scenario_outputs,
        exclusions=[],
        lineage=lineage,
    )
