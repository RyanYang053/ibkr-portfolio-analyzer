from __future__ import annotations

from typing import Any

from app.schemas.domain import AIReport, AccountSummary, Position, DISCLAIMER, utc_now
from app.services.ai.client import GeminiClient
from app.services.ai.prompt_templates import build_portfolio_memo_prompt, build_stock_analysis_prompt
from app.services.ai.structured_outputs import build_claim, build_structured_stock_context, evaluate_confidence_limits
from app.services.fundamentals.mock_provider import MockFundamentalProvider
from app.services.market_data.mock_provider import MockMarketDataProvider
from app.services.risk.portfolio_risk import analyze_portfolio_risk
from app.services.scoring.decision_engine import build_recommendation
from app.services.scoring.stock_score import score_stock
from app.services.technicals.indicators import calculate_technical_indicators


def generate_daily_portfolio_memo(summary: AccountSummary, positions: list[Position]) -> AIReport:
    risk = analyze_portfolio_risk(summary, positions)
    contributors = sorted(positions, key=lambda position: position.unrealized_pnl, reverse=True)[:3]
    detractors = sorted(positions, key=lambda position: position.unrealized_pnl)[:3]
    recommendations = [build_recommendation(position) for position in positions[:5]]

    report_json = {
        "title": "Daily Portfolio Memo",
        "portfolio_summary": f"Mock portfolio net liquidation is {summary.net_liquidation:.2f} {summary.base_currency}.",
        "macro_outlook": "Macro analysis requires Gemini connection to perform live search grounding on the current global situation.",
        "sector_dynamics": "Sector dynamics and trends are analyzed in real-time when the AI provider is active.",
        "daily_pnl_summary": "Daily P&L uses mock data in the MVP; live IBKR read-only support is a future connector.",
        "largest_contributors": [position.symbol for position in contributors],
        "largest_detractors": [position.symbol for position in detractors],
        "risk_alerts": [alert.model_dump() for alert in risk.alerts],
        "holdings_to_watch": [item.symbol for item in recommendations if item.action in {"Watch", "Trim Review", "Exit Review"}],
        "possible_add_zones": [item.add_zone for item in recommendations if item.action in {"Strong Add", "Add"}],
        "possible_trim_review_zones": [item.trim_review_zone for item in recommendations if item.action == "Trim Review"],
        "do_not_act_warnings": [
            "Outputs are based on mock data until live data providers are connected.",
            "Human review is required before any investment decision.",
            "The system does not submit orders to IBKR.",
        ],
        "cash_deployment_view": f"Cash is {risk.cash_percent:.2f}% of portfolio value.",
        "overall_portfolio_risk": f"Risk score is {risk.risk_score:.1f}/100.",
    }
    markdown = "\n".join(
        [
            "# Daily Portfolio Memo",
            report_json["portfolio_summary"],
            report_json["overall_portfolio_risk"],
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
    )


def generate_stock_research_report(position: Position, client: GeminiClient | None = None) -> dict[str, Any]:
    score = score_stock(position)
    recommendation = build_recommendation(position)
    context = _build_context(position, score, recommendation)
    gemini = client or GeminiClient()
    prompt = build_stock_analysis_prompt(position=context, score=None, recommendation=None)

    from app.services.ai.report_cache import set_cached_report

    if gemini.configured:
        try:
            report = gemini.generate_json(prompt)
            report.setdefault("symbol", position.symbol)
            report.setdefault("company", position.company_name)
            report.setdefault("final_score", score.final_score)
            report.setdefault("action", recommendation.action)
            report.setdefault("confidence", score.confidence)
            report.setdefault("human_review_required", True)
            report.setdefault("disclaimer", DISCLAIMER)
            report["provider"] = f"gemini:{gemini.model}"
            sanitized = _sanitize_ai_report(report, position, score, recommendation, context)
            set_cached_report(position.symbol, sanitized)
            return sanitized
        except Exception as exc:
            fallback = _fallback_stock_report(position, score, recommendation, context)
            fallback["provider_error"] = str(exc)
            set_cached_report(position.symbol, fallback)
            return fallback

    fallback = _fallback_stock_report(position, score, recommendation, context)
    set_cached_report(position.symbol, fallback)
    return fallback


def generate_ai_portfolio_memo(summary: AccountSummary, positions: list[Position], client: GeminiClient | None = None) -> dict[str, Any]:
    risk = analyze_portfolio_risk(summary, positions)
    recommendations = [build_recommendation(position) for position in positions]
    gemini = client or GeminiClient()
    prompt = build_portfolio_memo_prompt(summary=summary, positions=positions, risk=risk, recommendations=recommendations)
    from app.services.ai.report_cache import set_cached_report
    if gemini.configured:
        try:
            report = gemini.generate_json(prompt)
            report.setdefault("title", "AI Daily Portfolio Memo")
            report.setdefault("human_review_required", True)
            report.setdefault("disclaimer", DISCLAIMER)
            report["provider"] = f"gemini:{gemini.model}"
            set_cached_report("__PORTFOLIO__", report)
            return report
        except Exception as exc:
            fallback = generate_daily_portfolio_memo(summary, positions).report_json
            fallback["provider"] = "deterministic_fallback"
            fallback["provider_error"] = str(exc)
            fallback["disclaimer"] = DISCLAIMER
            fallback["human_review_required"] = True
            set_cached_report("__PORTFOLIO__", fallback)
            return fallback
    fallback = generate_daily_portfolio_memo(summary, positions).report_json
    fallback["provider"] = "deterministic_fallback"
    fallback["disclaimer"] = DISCLAIMER
    fallback["human_review_required"] = True
    set_cached_report("__PORTFOLIO__", fallback)
    return fallback


def _fallback_stock_report(position: Position, score, recommendation, context: dict[str, Any]) -> dict[str, Any]:
    limits = evaluate_confidence_limits(context)
    action = limits["action_override"] or recommendation.action
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
            f"The current deterministic score is {score.final_score:.1f}, interpreted as {score.interpretation}.",
            ["ev_stock_score"],
        ),
        build_claim(
            "claim_risk",
            "risk",
            "Risk review should focus on concentration, stale or missing data, and thesis invalidation triggers.",
            ["ev_data_quality", "ev_thesis", "ev_recommendation"],
        ),
    ]
    return {
        "schema_version": "stock_ai_analysis.v1",
        "symbol": position.symbol,
        "company": position.company_name,
        "portfolio_role": position.stock_type.replace("_", " "),
        "summary": f"{position.symbol} is reviewed through deterministic portfolio, scoring, risk, technical, valuation, and thesis data before AI interpretation.",
        "why_action": {"text": f"The rule engine category is {action} after applying data-quality and thesis rules.", "evidence_ids": ["ev_rule_engine", "ev_data_quality"]},
        "business_summary": f"{position.company_name} is held as a {position.stock_type.replace('_', ' ')} position in the mock portfolio.",
        "fundamental_view": "Live fundamentals are not connected yet; confidence is reduced.",
        "valuation_view": "Valuation view is based on deterministic mock scoring until Gemini and live data are configured.",
        "technical_view": "Technical view uses mock price and scoring inputs in the MVP.",
        "risk_view": "Review concentration, speculative exposure, stale data, and thesis invalidation triggers.",
        "portfolio_fit": f"Portfolio weight is {position.portfolio_weight:.2f}%.",
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
            {"text": f"Score interpretation is {score.interpretation}.", "evidence_ids": ["ev_stock_score"]},
            {"text": "The stored thesis has been compared against current data.", "evidence_ids": ["ev_thesis", "ev_rule_engine"]},
        ],
        "weaknesses": [
            {"text": f"Missing data categories: {', '.join(context['data_quality']['missing_categories']) or 'none'}.", "evidence_ids": ["ev_data_quality"]},
        ],
        "risks": [
            {"text": "Review data freshness, concentration, valuation, technical trend, and thesis invalidation triggers.", "evidence_ids": ["ev_rule_engine", "ev_thesis"]},
        ],
        "add_zone_explanation": {"text": "Add-zone output is suppressed when price data is missing; otherwise it follows rule-engine support/risk logic.", "evidence_ids": ["ev_data_quality", "ev_recommendation"]},
        "hold_zone_explanation": {"text": recommendation.hold_zone, "evidence_ids": ["ev_recommendation", "ev_thesis"]},
        "trim_review_explanation": {"text": recommendation.trim_review_zone, "evidence_ids": ["ev_recommendation", "ev_rule_engine"]},
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
    if limits["action_override"]:
        report["action"] = limits["action_override"]
    if not limits["add_zone_allowed"]:
        report["add_zone"] = None
    report["data_quality"] = context["data_quality"]
    report["thesis"] = context["thesis"]
    report["thesis_invalidation_triggers"] = context["thesis"]["invalidation_triggers"]
    report["evidence"] = context["evidence"]
    report["claims"] = _normalize_claims(report.get("claims"), context)
    report["human_review_required"] = True
    report["disclaimer"] = DISCLAIMER
    return report


def _build_context(position: Position, score, recommendation) -> dict[str, Any]:
    fundamentals = MockFundamentalProvider().get_fundamentals(position.symbol)
    valuation = {
        "pe_forward": fundamentals.pe_forward,
        "ev_sales": fundamentals.ev_sales,
        "fcf_yield": fundamentals.fcf_yield,
    }
    technicals = None
    if position.market_price > 0:
        try:
            history = MockMarketDataProvider().get_historical_prices(position.symbol, utc_now().date(), utc_now().date())
            technicals = calculate_technical_indicators(position.symbol, [item["close"] for item in history])
        except Exception:
            technicals = None
    try:
        catalysts = MockMarketDataProvider().get_recent_news(position.symbol)
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


def _min_confidence(value: str, cap: str) -> str:
    order = ["Low", "Medium", "Medium-High", "High"]
    if value not in order:
        value = "Medium"
    if cap not in order:
        cap = "Medium"
    return order[min(order.index(value), order.index(cap))]
