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

EVIDENCE_TEXT_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["text", "evidence_ids"],
}

STOCK_ANALYSIS_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "symbol": {"type": "string"},
        "company": {"type": "string"},
        "summary": EVIDENCE_TEXT_SCHEMA,
        "why_action": EVIDENCE_TEXT_SCHEMA,
        "business_summary": EVIDENCE_TEXT_SCHEMA,
        "fundamental_view": EVIDENCE_TEXT_SCHEMA,
        "valuation_view": EVIDENCE_TEXT_SCHEMA,
        "technical_view": EVIDENCE_TEXT_SCHEMA,
        "risk_view": EVIDENCE_TEXT_SCHEMA,
        "portfolio_fit": EVIDENCE_TEXT_SCHEMA,
        "action": {"type": "string"},
        "confidence": {"type": "string"},
        "strengths": {"type": "array", "items": EVIDENCE_TEXT_SCHEMA},
        "weaknesses": {"type": "array", "items": EVIDENCE_TEXT_SCHEMA},
        "risks": {"type": "array", "items": EVIDENCE_TEXT_SCHEMA},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "type": {"type": "string"},
                    "text": {"type": "string"},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id", "type", "text", "evidence_ids"],
            },
        },
        "missing_data": {"type": "array", "items": {"type": "string"}},
        "human_review_required": {"type": "boolean"},
        "disclaimer": {"type": "string"},
    },
    "required": [
        "symbol",
        "company",
        "summary",
        "why_action",
        "business_summary",
        "fundamental_view",
        "valuation_view",
        "technical_view",
        "risk_view",
        "portfolio_fit",
        "action",
        "confidence",
        "strengths",
        "weaknesses",
        "risks",
        "claims",
        "missing_data",
        "human_review_required",
        "disclaimer",
    ],
}


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
        "summary": {"text": "string", "evidence_ids": ["ev_*"]},
        "why_action": {"text": "string", "evidence_ids": ["ev_*"]},
        "business_summary": {"text": "string", "evidence_ids": ["ev_*"]},
        "fundamental_view": {"text": "string", "evidence_ids": ["ev_*"]},
        "valuation_view": {"text": "string", "evidence_ids": ["ev_*"]},
        "technical_view": {"text": "string", "evidence_ids": ["ev_*"]},
        "risk_view": {"text": "string", "evidence_ids": ["ev_*"]},
        "portfolio_fit": {"text": "string", "evidence_ids": ["ev_*"]},
        "final_score": "number | null",
        "rule_engine_action": "Strong Add | Add | Hold | Watch | Trim Review | Exit Review | Avoid | Data Insufficient",
        "action": "Strong Add | Add | Hold | Watch | Trim Review | Exit Review | Avoid | Data Insufficient",
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
        "summary": {
            "net_liquidation": summary.net_liquidation,
            "cash": summary.cash,
            "total_unrealized_pnl": summary.total_unrealized_pnl,
            "total_realized_pnl": summary.total_realized_pnl,
            "base_currency": summary.base_currency,
            "data_timestamp": summary.data_timestamp.isoformat(),
        },
        "positions": [
            {
                "symbol": position.symbol,
                "company_name": position.company_name,
                "asset_class": position.asset_class,
                "market_price": position.market_price,
                "market_value": position.market_value,
                "unrealized_pnl": position.unrealized_pnl,
                "currency": position.currency,
                "sector": position.sector,
                "industry": position.industry,
                "portfolio_weight": position.portfolio_weight,
                "stock_type": position.stock_type,
                "is_etf": position.is_etf,
                "is_speculative": position.is_speculative,
                "updated_at": position.updated_at.isoformat(),
            }
            for position in positions
        ],
        "risk": _jsonable(risk),
        "recommendations": [
            {
                "symbol": item.symbol,
                "action": item.action,
                "score": item.score,
                "confidence": item.confidence,
                "explanation": item.explanation,
                "evidence": item.evidence,
                "data_freshness": item.data_freshness,
            }
            for item in recommendations
        ],
        "required_disclaimer": DISCLAIMER,
        "data_boundary": {
            "structured_data_only": True,
            "broker_credentials_excluded": True,
            "order_data_excluded": True,
            "execution_instructions_forbidden": True,
        },
    }

    try:
        from app.services.suitability.engine import get_investor_profile, check_position_suitability
        from app.services.policy.engine import get_portfolio_policy, analyze_policy_drift

        active_id = getattr(summary, "account_id", "default")
        profile = get_investor_profile(active_id)
        policy = get_portfolio_policy(active_id)
        drift = analyze_policy_drift(positions, summary.cash, summary.net_liquidation, policy)

        suitability_warnings = []
        for pos in positions:
            suitability_warnings.extend(check_position_suitability(profile, pos))

        payload["investor_profile"] = {
            "objective": profile.objective,
            "time_horizon_years": profile.time_horizon_years,
            "risk_tolerance": profile.risk_tolerance,
            "risk_capacity": profile.risk_capacity,
            "liquidity_needs": profile.liquidity_needs,
            "account_type": profile.account_type,
            "restrictions": profile.restrictions,
        }
        payload["target_policy_ips"] = _jsonable(policy)
        payload["policy_drift_analysis"] = drift
        payload["suitability_warnings"] = suitability_warnings
    except Exception:
        pass

    try:
        from app.services.portfolio.pnl_tracker import get_pnl_history
        pnl_history = get_pnl_history(active_id)[-7:]
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
        + "Use this schema: title, portfolio_summary, macro_outlook, sector_dynamics, rebalancing_analysis, suitability_and_compliance, largest_contributors, largest_detractors, "
        + "risk_alerts, holdings_to_watch, possible_add_zones, possible_trim_review_zones, "
        + "cash_deployment_view, overall_portfolio_risk, "
        + "do_not_act_warnings, confidence, missing_data, human_review_required, disclaimer.\n"
        + "Instructions:\n"
        + "1. Use only the structured JSON below. Do not use outside facts or infer missing market conditions.\n"
        + "2. State that macro or sector analysis is unavailable when supporting catalyst data is absent.\n"
        + "3. Describe allocation drift as review flags only. Do not produce buy/sell quantities, order types, or execution instructions.\n"
        + "4. Evaluate suitability and data quality explicitly and require human review.\n\n"
        + json.dumps(payload, indent=2, sort_keys=True)
    )


OPTIONS_STRATEGY_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "symbol": {"type": "string"},
        "strategies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "e.g. Covered Call, Cash-Secured Put, Bull Call Spread"},
                    "type": {"type": "string", "description": "income | defensive | bullish | bearish"},
                    "expiration": {"type": "string", "description": "Expiration date format YYYY-MM-DD"},
                    "selected_strikes": {"type": "string", "description": "e.g. Sell 195 Call"},
                    "target_contract_symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Exact symbols from the provided options chain list, e.g. ['AAPL260717C00195000']"
                    },
                    "rationale": {"type": "string", "description": "Why this specific strategy and these strike contracts align with current stock metrics and research."},
                },
                "required": [
                    "name",
                    "type",
                    "expiration",
                    "selected_strikes",
                    "target_contract_symbols",
                    "rationale",
                ]
            }
        },
        "market_sentiment": {"type": "string", "description": "Educational summary of the volatility and market sentiment."},
        "human_review_required": {"type": "boolean"},
        "disclaimer": {"type": "string"}
    },
    "required": [
        "symbol",
        "strategies",
        "market_sentiment",
        "human_review_required",
        "disclaimer",
    ]
}


def build_options_strategy_prompt(*, symbol: str, current_price: float, trend: str, action: str, options_chain: list[dict[str, Any]]) -> str:
    payload = {
        "symbol": symbol,
        "current_price": current_price,
        "technical_trend": trend,
        "action_recommendation": action,
        "available_options_chain": options_chain,
        "required_disclaimer": DISCLAIMER,
    }
    return (
        "You are a professional options strategist designing educational options structures. Analyze the provided stock and options chain data.\n"
        + "Do not invent options contracts. You must select from the provided 'available_options_chain' list only.\n"
        + "Recommend two strategy candidates (one conservative income strategy e.g. Covered Call or Cash-Secured Put, and one risk-defined directional strategy e.g. Bull Call Spread or Bear Put Spread) that align with the technical trend and action.\n"
        + "Ensure you output only educational strategy candidates, never order recommendations or direct buy/sell commands.\n"
        + "Return strict JSON only. Do not wrap JSON in markdown.\n\n"
        + json.dumps(payload, indent=2, default=str)
    )


