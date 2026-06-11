import json
from typing import Any

from app.schemas.domain import Position, DISCLAIMER


STOCK_ANALYST_SYSTEM_FRAMEWORK = """
You are a professional investment research analyst for a read-only portfolio
intelligence system. Analyze securities using only the provided structured data.

Investment framework:
1. Business quality and portfolio role
2. Growth, profitability, cash flow, and balance sheet quality
3. Valuation reasonableness and valuation risk
4. Technical trend, support/resistance, and momentum
5. News/catalyst risk and data freshness
6. Portfolio fit, concentration, and speculative-risk budget
7. Thesis invalidation and human-review triggers

Rules:
- Do not invent financial facts.
- Separate facts from interpretation.
- Show missing or stale data.
- Do not create or submit orders.
- Do not recommend automatic trading.
- Do not say must buy or must sell.
- Use only decision-support language such as consider, review, watch,
  potential add zone, trim review, and exit review trigger.
- Always explain risk.
- Always require human review.
- Always state that the system does not execute trades.
"""


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def build_stock_analysis_prompt(*, position: Position, score: Any, recommendation: Any) -> str:
    if isinstance(position, dict):
        payload = dict(position)
    else:
        payload = {
            "position": _jsonable(position),
            "score": _jsonable(score),
            "recommendation": _jsonable(recommendation),
        }
    payload["required_disclaimer"] = DISCLAIMER
    payload["forbidden_context"] = ["broker_credentials", "account_passwords", "order_submission", "trade_execution"]
    payload["output_schema"] = {
        "schema_version": "stock_ai_analysis.v1",
        "symbol": "string",
        "company": "string",
        "portfolio_role": "string",
        "summary": "string",
        "why_action": {"text": "string", "evidence_ids": ["ev_*"]},
        "business_summary": "string",
        "fundamental_view": "string",
        "valuation_view": "string",
        "technical_view": "string",
        "risk_view": "string",
        "portfolio_fit": "string",
        "final_score": "number",
        "rule_engine_action": "Strong Add | Add | Hold | Watch | Trim Review | Exit Review | Avoid | Data Insufficient",
        "action": "Strong Add | Add | Hold | Watch | Trim Review | Exit Review | Avoid",
        "add_zone": "string",
        "hold_zone": "string",
        "trim_review_zone": "string",
        "exit_review_trigger": "string",
        "strengths": [{"text": "string", "evidence_ids": ["ev_*"]}],
        "weaknesses": [{"text": "string", "evidence_ids": ["ev_*"]}],
        "risks": [{"text": "string", "evidence_ids": ["ev_*"]}],
        "add_zone_explanation": {"text": "string", "evidence_ids": ["ev_*"]},
        "hold_zone_explanation": {"text": "string", "evidence_ids": ["ev_*"]},
        "trim_review_explanation": {"text": "string", "evidence_ids": ["ev_*"]},
        "confidence": "High | Medium-High | Medium | Low",
        "data_quality": "object",
        "thesis": {"status": "intact | weakened | broken"},
        "thesis_status": "intact | weakened | broken",
        "thesis_invalidation_triggers": ["string"],
        "claims": [{"id": "string", "type": "string", "text": "string", "evidence_ids": ["ev_*"]}],
        "evidence": [{"id": "ev_*", "category": "string", "source": "string", "timestamp": "string", "payload": {}}],
        "main_evidence": [{"text": "string", "evidence_ids": ["ev_*"]}],
        "main_risks": ["string"],
        "missing_data": ["string"],
        "data_freshness": {},
        "human_review_required": True,
        "disclaimer": DISCLAIMER,
    }
    return (
        STOCK_ANALYST_SYSTEM_FRAMEWORK
        + "\nReturn strict JSON only. Do not wrap JSON in markdown.\n"
        + "Every generated claim must include evidence_ids that reference the evidence array.\n"
        + "If confidence limits or action overrides are present in data_quality, obey them exactly.\n"
        + "Gemini receives only structured portfolio, risk, technical, fundamental, valuation, and catalyst data.\n"
        + "Do not request, infer, or mention broker credentials.\n"
        + "Analyze the stock using only the provided structured data:\n"
        + json.dumps(payload, indent=2, sort_keys=True)
    )


def build_portfolio_memo_prompt(*, summary: Any, positions: list[Position], risk: Any, recommendations: Any) -> str:
    payload = {
        "summary": _jsonable(summary),
        "positions": [_jsonable(position) for position in positions],
        "risk": _jsonable(risk),
        "recommendations": [_jsonable(item) for item in recommendations],
        "required_disclaimer": DISCLAIMER,
    }
    try:
        from app.services.portfolio.pnl_tracker import get_pnl_history
        pnl_history = get_pnl_history()[-7:]
        payload["performance_history"] = [
            {
                "date": entry.date,
                "net_liquidation": entry.net_liquidation,
                "cash": entry.cash,
                "daily_pnl": entry.daily_pnl,
                "daily_pnl_percent": entry.daily_pnl_percent
            }
            for entry in pnl_history
        ]
    except Exception:
        pass

    return (
        STOCK_ANALYST_SYSTEM_FRAMEWORK
        + "\nYou are writing a daily portfolio memo. Return strict JSON only.\n"
        + "Use this schema: title, portfolio_summary, macro_outlook, sector_dynamics, largest_contributors, largest_detractors, "
        + "risk_alerts, holdings_to_watch, possible_add_zones, possible_trim_review_zones, "
        + "cash_deployment_view, overall_portfolio_risk, "
        + "do_not_act_warnings, confidence, missing_data, human_review_required, disclaimer.\n"
        + "Instructions:\n"
        + "1. Use your search grounding capabilities to fetch the latest global economic updates (Fed interest rate trends, inflation figures, global GDP outlook) "
        + "and sector-specific updates for the assets currently held in the portfolio (such as Semiconductors, software, consumer tech, indices etc.).\n"
        + "2. Under 'macro_outlook', write a professional economic synthesis explaining current macro trends and how they impact equity risk premium and high-beta assets.\n"
        + "3. Under 'sector_dynamics', detail current trends (e.g. AI spending cycles, defensive sector rotations) impacting the portfolio's top sectors.\n"
        + "4. Synthesize the findings into the executive summary under 'portfolio_summary', incorporating analysis of the 'performance_history' trend.\n\n"
        + json.dumps(payload, indent=2, sort_keys=True)
    )

