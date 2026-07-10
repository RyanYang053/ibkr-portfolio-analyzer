from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.domain import (
    DataQualityContext,
    PortfolioResearchContext,
    SourceRecord,
)
from app.services.analytics.calculation_run import load_calculation_run


def build_portfolio_research_context(
    *,
    user_id: str,
    account_id: str,
    reporting_currency: str,
    performance: dict | None = None,
    attribution: dict | None = None,
    risk: dict | None = None,
    exposures: dict | None = None,
    holdings: list[dict] | None = None,
    events: list[dict] | None = None,
    policy: dict | None = None,
    suitability: dict | None = None,
    data_quality: DataQualityContext | None = None,
    sources: list[SourceRecord] | None = None,
    calculation_run_ids: list[str] | None = None,
) -> PortfolioResearchContext:
    run_ids = list(calculation_run_ids or [])
    for run_id in list(run_ids):
        if load_calculation_run(account_id, run_id) is None:
            run_ids.remove(run_id)

    return PortfolioResearchContext(
        user_id=user_id,
        account_id=account_id,
        as_of=datetime.now(timezone.utc),
        reporting_currency=reporting_currency,
        performance_summary=performance or {},
        attribution_summary=attribution or {},
        risk_summary=risk or {},
        exposure_summary=exposures or {},
        holdings=holdings or [],
        events=events or [],
        policy_summary=policy or {},
        suitability_summary=suitability or {},
        data_quality=data_quality
        or DataQualityContext(
            ledger_status="unknown",
            performance_status="unknown",
            risk_status="unknown",
            attribution_status="unknown",
        ),
        sources=sources or [],
        calculation_run_ids=run_ids,
    )
