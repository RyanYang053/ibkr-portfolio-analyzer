from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth_deps import get_current_principal
from app.api.deps import broker_not_configured_error, get_broker_adapter
from app.services.ai.report_generator import generate_daily_portfolio_memo
from app.services.broker.base import BrokerAdapter
from app.services.portfolio.account_scope import resolve_portfolio_account_id
from app.services.risk.portfolio_risk import analyze_portfolio_risk
from app.services.scoring.decision_engine import build_recommendation


from app.schemas.domain import AIReport, DISCLAIMER, utc_now


router = APIRouter(
    prefix="/reports",
    tags=["reports"],
    dependencies=[Depends(get_current_principal)],
)


def _data(adapter: BrokerAdapter, account_id: Optional[str] = None):
    try:
        active_id = resolve_portfolio_account_id(account_id, adapter)
        return adapter.get_account_summary(active_id), adapter.get_positions(active_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise broker_not_configured_error(exc) from exc


@router.get("")
def list_reports(
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
):
    summary, positions = _data(adapter, account_id)
    reports = [generate_daily_portfolio_memo(summary, positions)]

    # Load cached AI portfolio report if present
    from app.services.ai.report_cache import get_cached_report
    cached = get_cached_report("__PORTFOLIO__")
    if cached:
        # Clone cached to modify safely
        cached = dict(cached)
        provenance_obj = None
        if "provenance" in cached:
            prov = dict(cached["provenance"])
            prov["cached_data"] = True
            cached["provenance"] = prov
            from app.schemas.domain import Provenance
            provenance_obj = Provenance(**prov)

        # Build markdown text for the cached AI memo
        md_lines = [
            f"# {cached.get('title', 'AI Daily Portfolio Memo')}",
            f"**Provider**: {cached.get('provider', 'gemini')}",
            "",
            "## Summary",
            cached.get("portfolio_summary", ""),
            "",
            "## Holdings to Watch",
            ", ".join(cached.get("holdings_to_watch", [])) or "None",
            "",
            "## Possible Add Zones",
            "\n".join(f"- {zone}" for zone in cached.get("possible_add_zones", [])) or "None",
            "",
            "## Possible Trim Review Zones",
            "\n".join(f"- {zone}" for zone in cached.get("possible_trim_review_zones", [])) or "None",
        ]

        alerts = cached.get("risk_alerts", [])
        if alerts:
            md_lines.extend(["", "## Risk Alerts"])
            for alert in alerts:
                if isinstance(alert, dict):
                    md_lines.append(f"- **{alert.get('alert_type', 'Alert').replace('_', ' ').capitalize()}**: {alert.get('message', '')}")
                else:
                    md_lines.append(f"- {alert}")

        md_lines.extend(["", f"**Disclaimer**: {cached.get('disclaimer', DISCLAIMER)}"])

        reports.append(
            AIReport(
                report_type="ai_portfolio",
                title=cached.get("title", "AI Daily Portfolio Memo"),
                report_json=cached,
                report_markdown="\n".join(md_lines),
                data_timestamp=utc_now(),
                confidence=cached.get("confidence", "Medium"),
                missing_data=cached.get("missing_data", []),
                provenance=provenance_obj
            )
        )
    return reports



@router.post("/daily")
def daily(
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
):
    summary, positions = _data(adapter, account_id)
    return generate_daily_portfolio_memo(summary, positions)


@router.post("/weekly")
def weekly(
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
):
    summary, positions = _data(adapter, account_id)
    report = generate_daily_portfolio_memo(summary, positions)
    report.report_type = "weekly"
    report.title = "Weekly Investment Review"
    return report


@router.post("/stock/{symbol}")
def stock_report(
    symbol: str,
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
):
    _summary, positions = _data(adapter, account_id)
    for position in positions:
        if position.symbol == symbol.upper():
            return {"symbol": symbol.upper(), "recommendation": build_recommendation(position)}
    return {"status": "not_found"}


@router.post("/risk")
def risk_report(
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
):
    summary, positions = _data(adapter, account_id)
    return {"report_type": "risk", "risk": analyze_portfolio_risk(summary, positions)}
