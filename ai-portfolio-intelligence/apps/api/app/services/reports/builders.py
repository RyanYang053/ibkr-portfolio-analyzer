"""Structured report builders (plan §22).

Reports are assembled from existing engines. Every section carries a status so a
missing input is reported rather than silently omitted, and nothing is fabricated.
Output is structured JSON; a light HTML renderer is provided for export.
"""

from __future__ import annotations

import html
from typing import Any

from app.schemas.trade_plan import TradePlan


def _section(status: str, **data: Any) -> dict[str, Any]:
    return {"status": status, **data}


def build_monthly_review(
    *,
    account_id: str,
    as_of: str,
    summary: Any,
    risk: dict[str, Any] | None,
    journal_analytics: dict[str, Any] | None,
) -> dict[str, Any]:
    perf = _section(
        "available",
        net_liquidation=float(getattr(summary, "net_liquidation", 0) or 0),
        unrealized_pnl=float(getattr(summary, "total_unrealized_pnl", 0) or 0),
        base_currency=getattr(summary, "base_currency", "USD"),
    )
    risk_section = (
        _section(
            "available",
            risk_score=risk.get("risk_score"),
            alerts=risk.get("alerts", []),
            sector_exposure=risk.get("sector_exposure", {}),
        )
        if risk
        else _section("unavailable", note="Risk analysis unavailable.")
    )
    process = (
        _section("available", **(journal_analytics.get("metrics") or {}))
        if journal_analytics and journal_analytics.get("metrics")
        else _section(
            journal_analytics.get("status", "unavailable") if journal_analytics else "unavailable",
            note="Process analytics require enough closed journal trades.",
        )
    )
    return {
        "report_type": "monthly_investment_review",
        "account_id": account_id,
        "as_of": as_of,
        "performance": perf,
        "risk": risk_section,
        "allocation": _section("available", sector_exposure=(risk or {}).get("sector_exposure", {})),
        "trade_process_analytics": process,
        "tax_activity": _section("unavailable", note="Tax activity requires a reconciled tax year."),
        "goal_progress": _section("unavailable", note="Goal progress requires an approved financial plan."),
        "data_quality": {"status": "partial", "note": "Sections marked unavailable are withheld, not fabricated."},
    }


def build_trade_plan_report(plan: TradePlan) -> dict[str, Any]:
    checklist = plan.checklist.model_dump(mode="json") if plan.checklist else None
    return {
        "report_type": "trade_plan_report",
        "trade_plan_id": plan.trade_plan_id,
        "symbol": plan.symbol,
        "thesis": _section(
            "available" if (plan.thesis_version_id or plan.decision_packet_id) else "missing",
            thesis_version_id=plan.thesis_version_id,
            decision_packet_id=plan.decision_packet_id,
        ),
        "proposed_action": _section("available", direction=plan.direction.value, plan_type=plan.plan_type),
        "sizing": _section(
            "available" if plan.proposed_quantity is not None else "pending",
            method=plan.sizing_method.value if plan.sizing_method else None,
            proposed_quantity=plan.proposed_quantity,
            proposed_notional=plan.proposed_notional,
            maximum_loss=plan.maximum_loss,
        ),
        "scenarios": _section(
            "available" if (plan.target_low or plan.target_high) else "missing",
            entry_range=[plan.entry_low, plan.entry_high],
            invalidation=plan.invalidation_price,
            target_range=[plan.target_low, plan.target_high],
        ),
        "risks": _section("available", risks=plan.risks, catalysts=plan.catalysts),
        "portfolio_effect": _section("available", resulting_position=plan.resulting_position, liquidity=plan.liquidity_status),
        "tax_effect": _section("available" if plan.tax_estimate else "not_evaluated", tax_estimate=plan.tax_estimate),
        "readiness": _section("available" if checklist else "pending", checklist=checklist),
        "user_decision": _section("available", plan_status=plan.status.value),
        "order_generated": False,
    }


def render_report_html(report: dict[str, Any]) -> str:
    """Minimal self-contained HTML rendering of a structured report."""

    def render(value: Any, level: int = 2) -> str:
        if isinstance(value, dict):
            rows = "".join(
                f"<div><strong>{html.escape(str(k))}:</strong> {render(v, level + 1)}</div>"
                for k, v in value.items()
            )
            return f"<div style='margin-left:12px'>{rows}</div>"
        if isinstance(value, list):
            if not value:
                return "<em>none</em>"
            return "<ul>" + "".join(f"<li>{render(v, level + 1)}</li>" for v in value) + "</ul>"
        return html.escape(str(value))

    title = html.escape(str(report.get("report_type", "report")).replace("_", " ").title())
    return (
        "<!doctype html><meta charset='utf-8'>"
        f"<title>{title}</title>"
        "<body style='font-family:system-ui,sans-serif;max-width:820px;margin:2rem auto;color:#111'>"
        f"<h1>{title}</h1>{render(report)}"
        "<p style='color:#888;font-size:12px'>Read-only decision support. No orders are generated.</p>"
        "</body>"
    )
