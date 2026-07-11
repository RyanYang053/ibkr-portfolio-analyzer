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

METHODOLOGY_ID = "reit_nav_affo"
CODE_SHA = hashlib.sha256(b"reit_nav_affo_v1").hexdigest()


@dataclass(frozen=True)
class ReitNavAffoInputs:
    property_noi: Decimal | None
    cap_rate: Decimal | None
    net_debt: Decimal | None
    preferred_equity: Decimal | None
    share_count: Decimal | None
    affo_per_share: Decimal | None
    justified_affo_multiple: Decimal | None
    currency: str
    as_of: date
    source_ids: list[str]


def evaluate_reit_nav_affo(inputs: ReitNavAffoInputs, scenarios: list[ValuationScenario]) -> ValuationOutput:
    exclusions: list[str] = []
    lineage = ValuationInputLineage(
        source_ids=inputs.source_ids,
        as_of=inputs.as_of,
        currency=inputs.currency,
        share_count_source="share_count",
        field_lineage={
            "property_noi": inputs.source_ids,
            "affo_per_share": inputs.source_ids,
            "net_debt": inputs.source_ids,
        },
        methodology_id=METHODOLOGY_ID,
        methodology_version="1.0.0",
        code_sha=CODE_SHA,
    )

    positive_decimal(inputs.property_noi, "property_noi", exclusions)
    positive_decimal(inputs.cap_rate, "cap_rate", exclusions)
    if inputs.net_debt is None:
        exclusions.append("net_debt_unavailable")
    positive_decimal(inputs.share_count, "share_count", exclusions)
    if inputs.affo_per_share is None:
        exclusions.append("affo_or_ffo_per_share_unavailable")
    positive_decimal(inputs.justified_affo_multiple, "justified_affo_multiple", exclusions)
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
        exclusions.append("reit_valuation_model_not_validated")
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
        cap_rate = scenario.assumptions.get("cap_rate", inputs.cap_rate or Decimal("0"))
        affo_multiple = scenario.assumptions.get("justified_affo_multiple", inputs.justified_affo_multiple or Decimal("0"))
        noi = inputs.property_noi or Decimal("0")
        gross_asset_value = noi / cap_rate
        net_debt = inputs.net_debt or Decimal("0")
        preferred = inputs.preferred_equity or Decimal("0")
        equity_value = gross_asset_value - net_debt - preferred
        shares = inputs.share_count or Decimal("0")
        nav_per_share = equity_value / shares if shares > 0 else Decimal("0")
        affo_value = (inputs.affo_per_share or Decimal("0")) * affo_multiple
        per_share = (nav_per_share + affo_value) / Decimal("2")
        scenario_outputs.append(
            ScenarioValuation(
                name=scenario.name,
                per_share_value=per_share,
                enterprise_value=gross_asset_value,
                equity_value=equity_value,
                assumptions={"cap_rate": cap_rate, "justified_affo_multiple": affo_multiple},
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
