from __future__ import annotations

from typing import Any

from app.schemas.domain import AIReport, AccountSummary, Position, DISCLAIMER, utc_now, Provenance
from app.services.ai.client import GeminiClient
from app.services.ai.prompt_templates import (
    STOCK_ANALYSIS_RESPONSE_SCHEMA,
    build_portfolio_memo_prompt,
    build_stock_analysis_prompt,
)
from app.services.ai.structured_outputs import build_claim, build_structured_stock_context, evaluate_confidence_limits
from app.services.fundamentals.mock_provider import MockFundamentalProvider
from app.services.market_data.mock_provider import MockMarketDataProvider
from app.services.risk.portfolio_risk import analyze_portfolio_risk
from app.services.scoring.decision_engine import build_recommendation
from app.services.scoring.stock_score import score_stock
from app.services.technicals.indicators import calculate_technical_indicators
from app.core.config import settings


def generate_daily_portfolio_memo(summary: AccountSummary, positions: list[Position]) -> AIReport:
    risk = analyze_portfolio_risk(summary, positions)
    contributors = sorted(positions, key=lambda position: position.unrealized_pnl, reverse=True)[:3]
    detractors = sorted(positions, key=lambda position: position.unrealized_pnl)[:3]
    recommendations = [build_recommendation(position) for position in positions[:5]]

    is_demo = settings.broker_mode == "mock_ibkr_readonly"
    is_live_portfolio = not is_demo and summary.account_id not in ("MOCK-001", "MOCK-002", "SYNTHETIC_RESEARCH", "WATCHLIST_ONLY", "all")
    is_live_market = not is_demo
    is_mock_fallback = is_demo

    provenance = Provenance(
        live_portfolio_data=is_live_portfolio,
        live_market_data=is_live_market,
        cached_data=False,
        mock_fallback_data=is_mock_fallback,
        web_grounded_context=False
    )

    from app.services.suitability.engine import get_investor_profile, check_position_suitability
    from app.services.policy.engine import get_portfolio_policy, analyze_policy_drift
    from app.services.guardrails.engine import append_compliance_disclaimer

    active_id = summary.account_id or "default"
    profile = get_investor_profile(active_id)
    policy = get_portfolio_policy(active_id)
    drift = analyze_policy_drift(positions, summary.cash, summary.net_liquidation, policy)

    suitability_warnings = []
    for pos in positions:
        suitability_warnings.extend(check_position_suitability(profile, pos))

    rebalancing_text = (
        f"Portfolio asset drift: Equity: {drift['drifts']['equity']['drift']}%, Cash: {drift['drifts']['cash']['drift']}%. "
        "Any breach is an allocation-review flag only; no trade quantities or execution instructions are generated."
    )

    suitability_text = (
        f"Investor objective: {profile.objective}, risk tolerance: {profile.risk_tolerance}. "
        f"Suitability flags: {', '.join(suitability_warnings) or 'None (all positions suitable)'}."
    )

    report_json = {
        "title": "Daily Portfolio Memo",
        "portfolio_summary": f"Portfolio net liquidation is {summary.net_liquidation:.2f} {summary.base_currency}.",
        "macro_outlook": "Macro analysis requires Gemini connection to perform live economic updates and news grounding.",
        "sector_dynamics": "Sector dynamics and trends are analyzed in real-time when the AI provider is active.",
        "rebalancing_analysis": rebalancing_text,
        "suitability_and_compliance": suitability_text,
        "largest_contributors": [position.symbol for position in contributors],
        "largest_detractors": [position.symbol for position in detractors],
        "risk_alerts": [alert.model_dump() for alert in risk.alerts],
        "holdings_to_watch": [item.symbol for item in recommendations if item.action in {"Watch", "Trim Review", "Exit Review"}],
        "possible_add_zones": [item.add_zone for item in recommendations if item.action in {"Strong Add", "Add"} and item.add_zone],
        "possible_trim_review_zones": [item.trim_review_zone for item in recommendations if item.action == "Trim Review" and item.trim_review_zone],
        "do_not_act_warnings": [
            "Missing research categories remain unavailable until verified providers are connected.",
            "Human review is required before any investment decision.",
            "The system does not submit orders to IBKR.",
        ],
        "cash_deployment_view": f"Cash is {risk.cash_percent:.2f}% of portfolio value.",
        "overall_portfolio_risk": f"Risk score is {risk.risk_score:.1f}/100.",
        "provenance": provenance.model_dump()
    }
    
    report_json = append_compliance_disclaimer(report_json)
    
    markdown = "\n".join(
        [
            "# Daily Portfolio Memo",
            report_json["portfolio_summary"],
            f"## Rebalancing:\n{rebalancing_text}",
            f"## Suitability:\n{suitability_text}",
            f"Risk score is {risk.risk_score:.1f}/100.",
            "Decision-support only. Human review required.",
        ]
    )
    return AIReport(
        report_type="daily",
        title="Daily Portfolio Memo",
        report_json=report_json,
        report_markdown=markdown,
        data_timestamp=utc_now(),
        confidence="Medium",
        missing_data=["Live news", "Live fundamentals", "Live technical history"],
        provenance=provenance,
    )


def generate_stock_research_report(position: Position, client: GeminiClient | None = None) -> dict[str, Any]:
    score = score_stock(position)
    recommendation = build_recommendation(position)
    context = _build_context(position, score, recommendation)
    gemini = client or GeminiClient()
    prompt = build_stock_analysis_prompt(position=context, score=None, recommendation=None)

    from app.services.ai.report_cache import set_cached_report
    from app.core.config import settings
    is_demo = settings.broker_mode == "mock_ibkr_readonly"
    is_live_portfolio = not is_demo and position.account_id not in ("MOCK-001", "MOCK-002", "SYNTHETIC_RESEARCH", "WATCHLIST_ONLY")
    
    is_live_market = not is_demo and _context_has_live_market_data(context)
    is_mock_fallback = is_demo

    if gemini.configured:
        try:
            report = gemini.generate_json(prompt, response_schema=STOCK_ANALYSIS_RESPONSE_SCHEMA)
            report.setdefault("symbol", position.symbol)
            report.setdefault("company", position.company_name)
            report.setdefault("final_score", score.final_score)
            report.setdefault("action", recommendation.action)
            report.setdefault("confidence", score.confidence)
            report.setdefault("human_review_required", True)
            report.setdefault("disclaimer", DISCLAIMER)
            report["provider"] = f"gemini:{gemini.model}"
            report["provenance"] = {
                "live_portfolio_data": is_live_portfolio,
                "live_market_data": is_live_market,
                "cached_data": False,
                "mock_fallback_data": is_mock_fallback,
                "web_grounded_context": gemini.last_grounding_used
            }
            sanitized = _sanitize_ai_report(report, position, score, recommendation, context)
            set_cached_report(position.symbol, sanitized)
            return sanitized
        except Exception as exc:
            fallback = _fallback_stock_report(position, score, recommendation, context)
            fallback["provider_error"] = str(exc)
            fallback["provenance"] = {
                "live_portfolio_data": is_live_portfolio,
                "live_market_data": is_live_market,
                "cached_data": False,
                "mock_fallback_data": is_mock_fallback,
                "web_grounded_context": False
            }
            set_cached_report(position.symbol, fallback)
            return fallback

    fallback = _fallback_stock_report(position, score, recommendation, context)
    fallback["provenance"] = {
        "live_portfolio_data": is_live_portfolio,
        "live_market_data": is_live_market,
        "cached_data": False,
        "mock_fallback_data": is_mock_fallback,
        "web_grounded_context": False
    }
    set_cached_report(position.symbol, fallback)
    return fallback


def generate_ai_portfolio_memo(summary: AccountSummary, positions: list[Position], client: GeminiClient | None = None) -> dict[str, Any]:
    risk = analyze_portfolio_risk(summary, positions)
    recommendations = [build_recommendation(position) for position in positions]
    gemini = client or GeminiClient()
    prompt = build_portfolio_memo_prompt(summary=summary, positions=positions, risk=risk, recommendations=recommendations)
    
    from app.services.ai.report_cache import set_cached_report
    from app.core.config import settings
    is_demo = settings.broker_mode == "mock_ibkr_readonly"
    is_live_portfolio = not is_demo and summary.account_id not in ("MOCK-001", "MOCK-002", "SYNTHETIC_RESEARCH", "WATCHLIST_ONLY", "all")
    is_live_market = not is_demo
    is_mock_fallback = is_demo

    if gemini.configured:
        try:
            report = gemini.generate_json(prompt)
            report.setdefault("title", "AI Daily Portfolio Memo")
            report.setdefault("human_review_required", True)
            report.setdefault("disclaimer", DISCLAIMER)
            report["provider"] = f"gemini:{gemini.model}"
            report["provenance"] = {
                "live_portfolio_data": is_live_portfolio,
                "live_market_data": is_live_market,
                "cached_data": False,
                "mock_fallback_data": is_mock_fallback,
                "web_grounded_context": gemini.last_grounding_used
            }
            from app.services.guardrails.engine import append_compliance_disclaimer
            report = append_compliance_disclaimer(report)
            set_cached_report("__PORTFOLIO__", report)
            return report
        except Exception as exc:
            fallback = generate_daily_portfolio_memo(summary, positions).report_json
            fallback["provenance"] = {
                "live_portfolio_data": is_live_portfolio,
                "live_market_data": is_live_market,
                "cached_data": False,
                "mock_fallback_data": is_mock_fallback,
                "web_grounded_context": False
            }
            fallback["provider"] = "deterministic_fallback"
            fallback["provider_error"] = str(exc)
            fallback["disclaimer"] = DISCLAIMER
            fallback["human_review_required"] = True
            set_cached_report("__PORTFOLIO__", fallback)
            return fallback

    fallback = generate_daily_portfolio_memo(summary, positions).report_json
    fallback["provenance"] = {
        "live_portfolio_data": is_live_portfolio,
        "live_market_data": is_live_market,
        "cached_data": False,
        "mock_fallback_data": is_mock_fallback,
        "web_grounded_context": False
    }
    fallback["provider"] = "deterministic_fallback"
    fallback["disclaimer"] = DISCLAIMER
    fallback["human_review_required"] = True
    set_cached_report("__PORTFOLIO__", fallback)
    return fallback


def _fallback_stock_report(position: Position, score, recommendation, context: dict[str, Any]) -> dict[str, Any]:
    limits = evaluate_confidence_limits(context)
    action = limits["action_override"] or recommendation.action
    
    from app.services.suitability.engine import get_investor_profile, check_position_suitability
    from app.services.guardrails.engine import apply_recommendation_guardrails, append_compliance_disclaimer
    profile = get_investor_profile(position.account_id)
    suitability_warnings = check_position_suitability(profile, position)
    action, override_reason = apply_recommendation_guardrails(action, position.symbol, suitability_warnings)
    
    confidence = _min_confidence("Medium", limits["confidence_cap"])
    add_zone = recommendation.add_zone if limits["add_zone_allowed"] else None
    claims = [
        build_claim(
            "claim_portfolio_role",
            "portfolio_role",
            f"{position.company_name} is held as a {position.stock_type.replace('_', ' ')} position.",
            ["ev_portfolio_position", "ev_thesis"],
        ),
        build_claim(
            "claim_score",
            "score",
            "No composite company-quality score is produced while required research inputs are unverified.",
            ["ev_stock_score"],
        ),
        build_claim(
            "claim_risk",
            "risk",
            "Risk review should focus on concentration, stale or missing data, and thesis invalidation triggers.",
            ["ev_data_quality", "ev_thesis", "ev_recommendation"],
        ),
    ]
    res = {
        "schema_version": "stock_ai_analysis.v1",
        "symbol": position.symbol,
        "company": position.company_name,
        "portfolio_role": position.stock_type.replace("_", " "),
        "summary": {"text": f"{position.symbol} has a portfolio-only review. Missing or unverified research inputs prevent an actionable category.", "evidence_ids": ["ev_data_quality", "ev_portfolio_position"]},
        "why_action": {"text": f"The rule engine category is {action} after applying data-quality and thesis rules.", "evidence_ids": ["ev_rule_engine", "ev_data_quality"]},
        "business_summary": {"text": f"{position.company_name} is classified as a {position.stock_type.replace('_', ' ')} portfolio position.", "evidence_ids": ["ev_portfolio_position"]},
        "fundamental_view": {"text": "Fundamental analysis is unavailable when a verified provider snapshot is missing.", "evidence_ids": ["ev_fundamentals", "ev_data_quality"]},
        "valuation_view": {"text": "Valuation analysis is unavailable when verified valuation inputs are missing.", "evidence_ids": ["ev_valuation", "ev_data_quality"]},
        "technical_view": {"text": "Technical analysis is unavailable when sufficient live price history is missing.", "evidence_ids": ["ev_technicals", "ev_data_quality"]},
        "risk_view": {"text": "Review concentration, speculative exposure, stale data, and thesis invalidation triggers.", "evidence_ids": ["ev_rule_engine", "ev_thesis"]},
        "portfolio_fit": {"text": f"Portfolio weight is {position.portfolio_weight:.2f}%.", "evidence_ids": ["ev_portfolio_position"]},
        "final_score": score.final_score,
        "scores": context["scores"],
        "rule_engine_action": recommendation.action,
        "action": action,
        "add_zone": add_zone,
        "hold_zone": recommendation.hold_zone,
        "trim_review_zone": recommendation.trim_review_zone,
        "exit_review_trigger": recommendation.exit_review_trigger,
        "confidence": confidence,
        "confidence_limits": limits,
        "data_quality": context["data_quality"],
        "thesis": context["thesis"],
        "thesis_invalidation_triggers": context["thesis"]["invalidation_triggers"],
        "strengths": [
            {"text": "The portfolio position and data-quality state are available for review.", "evidence_ids": ["ev_portfolio_position", "ev_data_quality"]},
            {"text": "The stored thesis has been compared against current data.", "evidence_ids": ["ev_thesis", "ev_rule_engine"]},
        ],
        "weaknesses": [
            {"text": f"Missing data categories: {', '.join(context['data_quality']['missing_categories']) or 'none'}.", "evidence_ids": ["ev_data_quality"]},
        ],
        "risks": [
            {"text": "Review data freshness, concentration, valuation, technical trend, and thesis invalidation triggers.", "evidence_ids": ["ev_rule_engine", "ev_thesis"]},
        ],
        "add_zone_explanation": {"text": "Add-zone output is suppressed when price data is missing; otherwise it follows rule-engine support/risk logic.", "evidence_ids": ["ev_data_quality", "ev_recommendation"]},
        "hold_zone_explanation": {"text": recommendation.hold_zone or "Unavailable until inputs are verified.", "evidence_ids": ["ev_recommendation", "ev_thesis"]},
        "trim_review_explanation": {"text": recommendation.trim_review_zone or "Unavailable until inputs are verified.", "evidence_ids": ["ev_recommendation", "ev_rule_engine"]},
        "claims": claims,
        "evidence": context["evidence"],
        "main_evidence": [{"text": item, "evidence_ids": ["ev_recommendation"]} for item in recommendation.evidence],
        "main_risks": score.missing_data,
        "missing_data": context["data_quality"]["missing_categories"],
        "data_freshness": recommendation.data_freshness,
        "human_review_required": True,
        "disclaimer": DISCLAIMER,
        "provider": "deterministic_fallback",
    }
    from app.services.guardrails.engine import append_compliance_disclaimer
    return append_compliance_disclaimer(res)


def _sanitize_ai_report(report: dict[str, Any], position: Position, score, recommendation, context: dict[str, Any]) -> dict[str, Any]:
    forbidden_terms = ["must buy", "must sell", "guaranteed profit", "risk-free", "execute this trade", "order submitted"]
    serialized = str(report).lower()
    if any(term in serialized for term in forbidden_terms):
        fallback = _fallback_stock_report(position, score, recommendation, context)
        fallback["provider"] = "deterministic_fallback_policy_violation"
        return fallback
    limits = evaluate_confidence_limits(context)
    report["schema_version"] = "stock_ai_analysis.v1"
    report["confidence"] = _min_confidence(str(report.get("confidence", "Medium")), limits["confidence_cap"])
    
    action = report.get("action") or recommendation.action
    if limits["action_override"]:
        action = limits["action_override"]
        
    # Apply suitability override if needed
    from app.services.suitability.engine import get_investor_profile, check_position_suitability
    from app.services.guardrails.engine import apply_recommendation_guardrails, append_compliance_disclaimer
    profile = get_investor_profile(position.account_id)
    suitability_warnings = check_position_suitability(profile, position)
    action, override_reason = apply_recommendation_guardrails(action, position.symbol, suitability_warnings)
    report["action"] = action
    if override_reason:
        # Append override reason to summary or why_action
        why_text = report.get("why_action", {}).get("text", "") if isinstance(report.get("why_action"), dict) else str(report.get("why_action", ""))
        report["why_action"] = {
            "text": (why_text + " " + override_reason).strip(),
            "evidence_ids": ["ev_rule_engine", "ev_data_quality"]
        }
        
    if not limits["add_zone_allowed"]:
        report["add_zone"] = None
    else:
        report["add_zone"] = recommendation.add_zone
    report["hold_zone"] = recommendation.hold_zone
    report["trim_review_zone"] = recommendation.trim_review_zone
    report["exit_review_trigger"] = recommendation.exit_review_trigger
    report["data_quality"] = context["data_quality"]
    report["thesis"] = context["thesis"]
    report["thesis_invalidation_triggers"] = context["thesis"]["invalidation_triggers"]
    report["evidence"] = context["evidence"]
    report["claims"] = _normalize_claims(report.get("claims"), context)
    for field in (
        "summary",
        "why_action",
        "business_summary",
        "fundamental_view",
        "valuation_view",
        "technical_view",
        "risk_view",
        "portfolio_fit",
        "add_zone_explanation",
        "hold_zone_explanation",
        "trim_review_explanation",
    ):
        report[field] = _normalize_evidence_text(report.get(field), context)
    for field in ("strengths", "weaknesses", "risks", "main_evidence"):
        report[field] = _normalize_evidence_list(report.get(field), context)
    report["human_review_required"] = True
    
    return append_compliance_disclaimer(report)


def _build_context(position: Position, score, recommendation) -> dict[str, Any]:
    from app.core.config import settings
    import sys
    allow_mock = (settings.broker_mode == "mock_ibkr_readonly") or ("pytest" in sys.modules)

    try:
        fundamentals = MockFundamentalProvider(allow_mock=allow_mock).get_fundamentals(position.symbol)
    except Exception:
        fundamentals = None
    valuation = (
        {
            "pe_forward": fundamentals.pe_forward,
            "ev_sales": fundamentals.ev_sales,
            "fcf_yield": fundamentals.fcf_yield,
            "source": fundamentals.source,
        }
        if fundamentals
        else None
    )
    technicals = None
    if position.market_price > 0:
        try:
            history = MockMarketDataProvider(allow_mock=allow_mock).get_historical_prices(position.symbol, utc_now().date(), utc_now().date())
            technicals = calculate_technical_indicators(position.symbol, [item["close"] for item in history])
        except Exception:
            technicals = None
    try:
        catalysts = MockMarketDataProvider(allow_mock=allow_mock).get_recent_news(position.symbol)
    except Exception:
        catalysts = None
    return build_structured_stock_context(
        position=position,
        score=score,
        recommendation=recommendation,
        technicals=technicals,
        fundamentals=fundamentals,
        valuation=valuation,
        catalysts=catalysts,
        portfolio_timestamp=position.updated_at,
    )


def _context_has_live_market_data(context: dict[str, Any]) -> bool:
    fundamentals = context.get("fundamentals")
    catalysts = context.get("catalysts")
    fundamental_live = isinstance(fundamentals, dict) and fundamentals.get("source") == "live_yahoo_finance"
    catalyst_live = isinstance(catalysts, list) and any(
        isinstance(item, dict) and item.get("source") not in {None, "mock_news"}
        for item in catalysts
    )
    return fundamental_live or catalyst_live


def _normalize_claims(claims: Any, context: dict[str, Any]) -> list[dict[str, Any]]:
    evidence_ids = {item["id"] for item in context["evidence"]}
    normalized: list[dict[str, Any]] = []
    if isinstance(claims, list):
        for index, claim in enumerate(claims):
            if not isinstance(claim, dict):
                continue
            claim_ids = [item for item in claim.get("evidence_ids", []) if item in evidence_ids]
            if not claim_ids:
                claim_ids = ["ev_data_quality"]
            normalized.append(
                {
                    "id": str(claim.get("id", f"claim_{index}")),
                    "type": str(claim.get("type", "analysis")),
                    "text": str(claim.get("text", "")),
                    "evidence_ids": claim_ids,
                }
            )
    if normalized:
        return normalized
    return [
        build_claim("claim_ai_summary", "analysis", "AI output was normalized to preserve evidence traceability.", ["ev_data_quality"])
    ]


def _normalize_evidence_text(value: Any, context: dict[str, Any]) -> dict[str, Any]:
    valid_ids = {item["id"] for item in context["evidence"]}
    if isinstance(value, dict):
        text = str(value.get("text", ""))
        evidence_ids = [item for item in value.get("evidence_ids", []) if item in valid_ids]
    else:
        text = str(value or "")
        evidence_ids = []
    return {
        "text": text,
        "evidence_ids": evidence_ids or ["ev_data_quality"],
    }


def _normalize_evidence_list(value: Any, context: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [_normalize_evidence_text(item, context) for item in value]


def _min_confidence(value: str, cap: str) -> str:
    order = ["Low", "Medium", "Medium-High", "High"]
    if value not in order:
        value = "Medium"
    if cap not in order:
        cap = "Medium"
    return order[min(order.index(value), order.index(cap))]
