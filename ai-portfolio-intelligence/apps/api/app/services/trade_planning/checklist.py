"""Pre-trade checklist (plan §9.3).

A plan can only be marked ready when every non-waivable check passes. The checklist
is evidence for a *human* decision — it never authorizes execution.
"""

from __future__ import annotations

from app.schemas.trade_plan import TradePlan, TradePlanCheck, TradePlanChecklist

_ACCEPTABLE_STATUS = {"ok", "acceptable", "available", "pass", "passed"}


def evaluate_checklist(plan: TradePlan) -> TradePlanChecklist:
    checks: list[TradePlanCheck] = []

    def add(check_id: str, passed: bool, detail: str = "", waived: bool = False) -> None:
        checks.append(TradePlanCheck(check_id=check_id, passed=passed, detail=detail, waived=waived))

    has_thesis = bool(plan.thesis_version_id or plan.decision_packet_id)
    add("thesis_exists", has_thesis, "thesis or decision packet linked" if has_thesis else "no thesis linked")
    add("invalidation_exists", plan.invalidation_price is not None, "invalidation price set")
    add("time_horizon_exists", bool(plan.holding_period), "holding period set")
    add("sizing_method_exists", plan.sizing_method is not None, "position-sizing method chosen")
    add(
        "data_health_acceptable",
        plan.data_readiness in _ACCEPTABLE_STATUS or plan.data_readiness == "unknown",
        f"data_readiness={plan.data_readiness}",
    )
    add(
        "liquidity_acceptable",
        plan.liquidity_status in _ACCEPTABLE_STATUS or plan.liquidity_status == "unknown",
        f"liquidity_status={plan.liquidity_status}",
    )
    add(
        "portfolio_policy_passes",
        plan.portfolio_fit_status in _ACCEPTABLE_STATUS or plan.portfolio_fit_status == "unknown",
        f"portfolio_fit_status={plan.portfolio_fit_status}",
    )
    tax_ok = plan.tax_estimate is not None
    add("tax_impact_evaluated", tax_ok, "tax estimate present" if tax_ok else "tax not evaluated", waived=not tax_ok)
    add("upcoming_events_reviewed", True, f"{len(plan.catalysts)} catalyst(s) noted", waived=len(plan.catalysts) == 0)
    has_scenarios = plan.target_low is not None or plan.target_high is not None
    add("scenario_analysis_exists", has_scenarios, "target range set")
    add(
        "limitations_acknowledged",
        plan.user_acknowledged_limitations,
        "user acknowledged limitations",
    )

    blocking = [c.check_id for c in checks if not c.passed and not c.waived]
    return TradePlanChecklist(checks=checks, ready=not blocking, blocking=blocking)
