from __future__ import annotations

import math
from datetime import date
from typing import Any

from app.core.config import settings
from app.schemas.domain import DISCLAIMER, AccountSummary, AIReport, Position, Provenance, utc_now
from app.services.ai.client import GeminiClient
from app.services.ai.prompt_templates import (
    OPTIONS_STRATEGY_RESPONSE_SCHEMA,
    STOCK_ANALYSIS_RESPONSE_SCHEMA,
    build_options_strategy_prompt,
    build_portfolio_memo_prompt,
    build_stock_analysis_prompt,
)
from app.services.ai.structured_outputs import build_claim, build_structured_stock_context, evaluate_confidence_limits
from app.services.fundamentals.providers import get_fundamental_provider
from app.services.market_data.mock_provider import MockMarketDataProvider
from app.services.provenance import build_report_provenance
from app.services.risk.portfolio_risk import analyze_portfolio_risk
from app.services.scoring.decision_engine import build_recommendation
from app.services.scoring.stock_score import score_stock
from app.services.technicals.indicators import calculate_technical_indicators


def _derive_provenance(positions: list[Position], *, web_grounded: bool = False) -> Provenance:
    return build_report_provenance(positions, web_grounded=web_grounded)


def generate_daily_portfolio_memo(
    summary: AccountSummary,
    positions: list[Position],
    *,
    user_id: str = "local-dev",
    calculation_run_ids: list[str] | None = None,
) -> AIReport:
    risk = analyze_portfolio_risk(summary, positions)
    from app.services.portfolio.period_contributors import period_position_contributors
    from app.services.portfolio.pnl_tracker import get_pnl_history

    history = get_pnl_history(summary.account_id or "default")
    contributors, detractors = period_position_contributors(history)
    if not contributors:
        contributors = [position.symbol for position in sorted(positions, key=lambda p: p.unrealized_pnl, reverse=True)[:3]]
    if not detractors:
        detractors = [position.symbol for position in sorted(positions, key=lambda p: p.unrealized_pnl)[:3]]
    recommendations = [build_recommendation(position) for position in positions[:5]]

    provenance = _derive_provenance(positions)

    from app.services.broker.ibkr_readonly import get_exchange_rate
    from app.services.guardrails.engine import append_compliance_disclaimer
    from app.services.policy.engine import analyze_policy_drift, get_portfolio_policy
    from app.services.suitability.engine import check_position_suitability, get_investor_profile

    active_id = summary.account_id or "default"
    profile = get_investor_profile(active_id, user_id=user_id)
    policy = get_portfolio_policy(active_id, user_id=user_id)
    drift = analyze_policy_drift(
        positions,
        summary.cash,
        summary.net_liquidation,
        policy,
        base_currency=summary.base_currency,
        fx_resolver=get_exchange_rate,
    )

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
        "largest_contributors": contributors,
        "largest_detractors": detractors,
        "contributor_basis": "period_unrealized_pnl_change" if len(history) >= 2 else "current_unrealized_pnl_snapshot",
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
        "calculation_run_ids": calculation_run_ids or [],
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


def generate_stock_research_report(
    position: Position,
    client: GeminiClient | None = None,
    *,
    user_id: str = "local-dev",
    account_id: str | None = None,
) -> dict[str, Any]:
    score = score_stock(position)
    recommendation = build_recommendation(position)
    context = _build_context(position, score, recommendation, user_id=user_id)
    gemini = client or GeminiClient()
    prompt = build_stock_analysis_prompt(position=context, score=None, recommendation=None)

    from app.services.ai.report_cache import set_cached_report
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
            sanitized = _sanitize_ai_report(report, position, score, recommendation, context, user_id=user_id)
            set_cached_report(
                position.symbol,
                sanitized,
                user_id=user_id,
                account_id=account_id or position.account_id,
            )
            return sanitized
        except Exception as exc:
            fallback = _fallback_stock_report(position, score, recommendation, context, user_id=user_id)
            fallback["provider_error"] = str(exc)
            fallback["provenance"] = {
                "live_portfolio_data": is_live_portfolio,
                "live_market_data": is_live_market,
                "cached_data": False,
                "mock_fallback_data": is_mock_fallback,
                "web_grounded_context": False
            }
            set_cached_report(
                position.symbol,
                fallback,
                user_id=user_id,
                account_id=account_id or position.account_id,
            )
            return fallback

    fallback = _fallback_stock_report(position, score, recommendation, context, user_id=user_id)
    fallback["provenance"] = {
        "live_portfolio_data": is_live_portfolio,
        "live_market_data": is_live_market,
        "cached_data": False,
        "mock_fallback_data": is_mock_fallback,
        "web_grounded_context": False
    }
    set_cached_report(
        position.symbol,
        fallback,
        user_id=user_id,
        account_id=account_id or position.account_id,
    )
    return fallback


def generate_ai_portfolio_memo(
    summary: AccountSummary,
    positions: list[Position],
    client: GeminiClient | None = None,
    *,
    user_id: str = "local-dev",
    calculation_run_ids: list[str] | None = None,
) -> dict[str, Any]:
    risk = analyze_portfolio_risk(summary, positions)
    recommendations = [build_recommendation(position) for position in positions]
    gemini = client or GeminiClient()
    prompt = build_portfolio_memo_prompt(
        summary=summary,
        positions=positions,
        risk=risk,
        recommendations=recommendations,
        user_id=user_id,
    )
    
    from app.services.ai.report_cache import set_cached_report
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
                "web_grounded_context": gemini.last_grounding_used,
                "calculation_run_ids": calculation_run_ids or [],
            }
            from app.services.guardrails.engine import append_compliance_disclaimer
            report = append_compliance_disclaimer(report)
            from app.services.governance.decision_journal import record_journal_from_ai_report

            record_journal_from_ai_report(
                user_id=user_id,
                account_id=summary.account_id or "all",
                report=report,
                calculation_run_ids=calculation_run_ids,
            )
            set_cached_report(
                "__PORTFOLIO__",
                report,
                user_id=user_id,
                account_id=summary.account_id or "all",
                report_type="portfolio",
            )
            return report
        except Exception as exc:
            fallback = generate_daily_portfolio_memo(
                summary,
                positions,
                user_id=user_id,
                calculation_run_ids=calculation_run_ids,
            ).report_json
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
            set_cached_report(
                "__PORTFOLIO__",
                fallback,
                user_id=user_id,
                account_id=summary.account_id or "all",
                report_type="portfolio",
            )
            return fallback

    fallback = generate_daily_portfolio_memo(
        summary,
        positions,
        user_id=user_id,
        calculation_run_ids=calculation_run_ids,
    ).report_json
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
    set_cached_report(
        "__PORTFOLIO__",
        fallback,
        user_id=user_id,
        account_id=summary.account_id or "all",
        report_type="portfolio",
    )
    return fallback


def _fallback_stock_report(position: Position, score, recommendation, context: dict[str, Any], *, user_id: str) -> dict[str, Any]:
    limits = evaluate_confidence_limits(context)
    action = limits["action_override"] or recommendation.action
    
    from app.services.guardrails.engine import append_compliance_disclaimer, apply_recommendation_guardrails
    from app.services.suitability.engine import check_position_suitability, get_investor_profile
    profile = get_investor_profile(position.account_id, user_id=user_id)
    suitability_warnings = check_position_suitability(profile, position)
    action, override_reason = apply_recommendation_guardrails(action, position.symbol, suitability_warnings)
    
    confidence = _min_confidence("Medium", limits["confidence_cap"])
    add_zone = recommendation.add_zone if limits["add_zone_allowed"] else None
    invalidation_triggers = list(context["thesis"]["invalidation_triggers"])
    if not invalidation_triggers:
        invalidation_triggers = [
            "Revenue growth turns negative or materially below the stored assumption range",
            "Operating margin compression or balance-sheet stress versus stored assumptions",
            "Technical trend breakdown against the stored review framework",
        ]
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
        "thesis": {**context["thesis"], "invalidation_triggers": invalidation_triggers},
        "thesis_invalidation_triggers": invalidation_triggers,
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
    return append_compliance_disclaimer(res)


def _sanitize_ai_report(
    report: dict[str, Any],
    position: Position,
    score,
    recommendation,
    context: dict[str, Any],
    *,
    user_id: str,
) -> dict[str, Any]:
    forbidden_terms = ["must buy", "must sell", "guaranteed profit", "risk-free", "execute this trade", "order submitted"]
    serialized = str(report).lower()
    if any(term in serialized for term in forbidden_terms):
        fallback = _fallback_stock_report(position, score, recommendation, context, user_id=user_id)
        fallback["provider"] = "deterministic_fallback_policy_violation"
        return fallback
    limits = evaluate_confidence_limits(context)
    report["schema_version"] = "stock_ai_analysis.v1"
    report["confidence"] = _min_confidence(str(report.get("confidence", "Medium")), limits["confidence_cap"])
    
    action = report.get("action") or recommendation.action
    if limits["action_override"]:
        action = limits["action_override"]
        
    # Apply suitability override if needed
    from app.services.guardrails.engine import append_compliance_disclaimer, apply_recommendation_guardrails
    from app.services.suitability.engine import check_position_suitability, get_investor_profile
    profile = get_investor_profile(position.account_id, user_id=user_id)
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


def _build_context(position: Position, score, recommendation, *, user_id: str = "local-dev") -> dict[str, Any]:
    import sys
    allow_mock = (settings.broker_mode == "mock_ibkr_readonly") or ("pytest" in sys.modules)

    try:
        fundamentals = get_fundamental_provider(allow_mock=allow_mock).get_fundamentals(position.symbol)
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
            from datetime import timedelta

            end_date = utc_now().date()
            start_date = end_date - timedelta(days=500)
            history = MockMarketDataProvider(allow_mock=allow_mock).get_historical_prices(
                position.symbol,
                start_date,
                end_date,
            )
            closes = [float(item["close"]) for item in history if item.get("close") is not None]
            if len(closes) >= 252:
                technicals = calculate_technical_indicators(position.symbol, closes)
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
        user_id=user_id,
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


def generate_options_strategy_report(
    position: Position,
    technicals: dict[str, Any] | None,
    client: GeminiClient | None = None,
    cash_available: float = 15000.0,
    account_type: str = "Margin",
    account_currency: str | None = None,
) -> dict[str, Any]:
    from app.services.options.engine import (
        calculate_bear_put_spread_metrics,
        calculate_bull_call_spread_metrics,
        calculate_cash_secured_put_metrics,
        calculate_covered_call_metrics,
        evaluate_strategy_eligibility,
        generate_mock_options_chain,
    )
    from app.services.scoring.decision_engine import build_recommendation

    gemini = client or GeminiClient()
    rec = build_recommendation(position)
    reporting_currency = (account_currency or settings.default_reporting_currency).upper()
    
    # 1. Determine data source and fetch chain
    is_demo = settings.broker_mode == "mock_ibkr_readonly"
    is_live_portfolio = not is_demo and position.account_id not in ("MOCK-001", "MOCK-002", "SYNTHETIC_RESEARCH", "WATCHLIST_ONLY")
    is_live_market = not is_demo
    is_mock_fallback = is_demo

    # Deterministic or live option chain
    chain = []
    chain_source = "Mock"
    live_chain_unavailable = False
    if is_live_market:
        try:
            from app.services.options.ibkr_options_provider import resolve_options_chain

            resolution = resolve_options_chain(position.symbol, position.market_price)
            chain = resolution.contracts
            chain_source = resolution.selected_provider
            is_mock_fallback = False
        except Exception as exc:
            from app.services.options.chain_provider import OptionsChainUnavailable

            if isinstance(exc, OptionsChainUnavailable):
                from fastapi import HTTPException

                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": "LIVE_OPTIONS_CHAIN_UNAVAILABLE",
                        "message": (
                            f"Live options quotes are unavailable for {position.symbol.upper()}. "
                            "Strategy economics are withheld instead of simulated."
                        ),
                        "provider_attempts": exc.errors,
                    },
                ) from exc
            live_chain_unavailable = True
    if not chain and is_demo:
        chain = generate_mock_options_chain(position.symbol, position.market_price)
    if is_live_market and live_chain_unavailable:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=503,
            detail={
                "code": "LIVE_OPTIONS_CHAIN_UNAVAILABLE",
                "message": (
                    f"Live options quotes are unavailable for {position.symbol.upper()}. "
                    "Strategy economics are withheld instead of simulated."
                ),
            },
        )
    chain_dict = [c.model_dump() for c in chain]
    
    trend_str = "Neutral"
    if technicals and isinstance(technicals, dict) and technicals.get("trend_classification"):
        trend_str = str(technicals["trend_classification"])

    # Deterministic economics are always available when a chain exists.
    if not gemini.configured:
        from app.services.options.contract_filters import OptionLiquidityPolicy
        from app.services.options.deterministic_report import (
            _relaxed_policy_for_demo,
            build_deterministic_options_report,
        )

        deterministic = build_deterministic_options_report(
            position,
            chain,
            cash_available=cash_available,
            account_type=account_type,
            account_currency=reporting_currency,
            chain_source=chain_source,
            is_demo=is_demo,
            liquidity_policy=(
                _relaxed_policy_for_demo()
                if is_demo
                else OptionLiquidityPolicy()
            ),
        )
        if not is_demo:
            from app.db.iv_observation_repo import append_iv_history_json, iv_percentile
            from app.services.options.quantlib_benchmark import compare_with_internal_bs

            atm = min(chain, key=lambda item: abs(item.strike - position.market_price))
            days = max((atm.expiration - date.today()).days, 1)
            append_iv_history_json(
                position.symbol,
                atm.implied_volatility,
                source=chain_source,
                option_right=atm.right,
                days_to_expiry=days,
                delta=atm.delta,
                moneyness=round(position.market_price / atm.strike, 4) if atm.strike else None,
            )
            deterministic["iv_percentile"] = iv_percentile(
                position.symbol,
                atm.implied_volatility,
                option_right=atm.right,
                days_to_expiry=days,
            )
            deterministic["provenance"]["quantlib_benchmark"] = compare_with_internal_bs(
                spot=position.market_price,
                strike=atm.strike,
                days_to_expiry=days,
                risk_free_rate=0.045,
                volatility=atm.implied_volatility,
                right=atm.right,
            )
        if not settings.allow_mock_options_strategy and is_demo:
            return _fallback_options_report(
                position.symbol,
                position.market_price,
                "Gemini API key is not configured.",
                is_live_portfolio,
                is_live_market,
                is_mock_fallback,
            )
        return deterministic

    # 2. Build the LLM prompt using prevalidated candidates
    from app.services.options.contract_filters import OptionLiquidityPolicy
    from app.services.options.deterministic_report import (
        _relaxed_policy_for_demo,
        build_validated_strategy_candidates,
    )

    portfolio_base_currency = reporting_currency
    candidates = build_validated_strategy_candidates(
        position,
        chain,
        cash_available=cash_available,
        account_type=account_type,
        account_currency=portfolio_base_currency,
        is_demo=is_demo,
        liquidity_policy=(
            _relaxed_policy_for_demo()
            if is_demo
            else OptionLiquidityPolicy()
        ),
    )
    prompt = build_options_strategy_prompt(
        symbol=position.symbol,
        current_price=position.market_price,
        trend=trend_str,
        action=rec.action,
        options_chain=chain_dict,
        options_candidates=candidates,
    )

    try:
        report = gemini.generate_json(prompt, response_schema=OPTIONS_STRATEGY_RESPONSE_SCHEMA)
        
        contract_by_symbol = {contract.symbol: contract for contract in chain}
        from datetime import datetime, timezone

        from app.services.broker.ibkr_readonly import get_exchange_rate
        from app.services.options.contract_filters import is_liquid

        liquidity_policy = OptionLiquidityPolicy() if not is_demo else _relaxed_policy_for_demo()
        now = datetime.now(timezone.utc)
        validated_strategies = []
        for strat in report.get("strategies", []):
            contract_symbols = strat.get("target_contract_symbols", [])
            if not contract_symbols:
                continue
            selected_contracts = [
                contract_by_symbol[symbol]
                for symbol in contract_symbols
                if symbol in contract_by_symbol
            ]
            if not selected_contracts:
                continue
            if len(selected_contracts) != len(contract_symbols):
                continue
            if not all(is_liquid(contract, liquidity_policy, now=now) for contract in selected_contracts):
                continue

            strat_name = strat.get("name", "")
            strat_name_lower = strat_name.lower()
            if "spread" in strat_name_lower:
                if len(selected_contracts) != 2:
                    continue
                if (
                    selected_contracts[0].expiration != selected_contracts[1].expiration
                    or selected_contracts[0].right != selected_contracts[1].right
                    or selected_contracts[0].multiplier != selected_contracts[1].multiplier
                    or (selected_contracts[0].currency or position.currency) != (selected_contracts[1].currency or position.currency)
                    or (selected_contracts[0].underlying_symbol or position.symbol) != (selected_contracts[1].underlying_symbol or position.symbol)
                ):
                    continue

            main_contract = selected_contracts[0]
            strike = main_contract.strike
            premium = main_contract.mid
            multiplier = float(main_contract.multiplier or 100.0)
            contract_currency = main_contract.currency or position.currency
            account_currency = portfolio_base_currency
            fx_rate = get_exchange_rate(contract_currency, account_currency)
            net_premium = abs(premium)
            premium_type = "credit"
            max_profit = ""
            max_loss = ""
            breakeven = strike
            
            if "covered call" in strat_name_lower:
                metrics = calculate_covered_call_metrics(
                    position.market_price,
                    strike,
                    premium,
                    multiplier=multiplier,
                )
                max_profit_per_share = strike - position.market_price + premium
                if max_profit_per_share < 0:
                    continue
                max_profit = metrics["max_profit"]
                max_loss = metrics["max_loss"]
                breakeven = metrics["breakeven"]
                net_premium = abs(premium)
                premium_type = "credit"
            elif "cash-secured put" in strat_name_lower:
                metrics = calculate_cash_secured_put_metrics(strike, premium, multiplier=multiplier)
                max_profit = metrics["max_profit"]
                max_loss = metrics["max_loss"]
                breakeven = metrics["breakeven"]
                net_premium = abs(premium)
                premium_type = "credit"
            elif "spread" in strat_name_lower:
                leg1, leg2 = selected_contracts[0], selected_contracts[1]
                leg_multiplier = float(leg1.multiplier or 100.0)
                if main_contract.right == "C":
                    long_leg = leg1 if leg1.strike < leg2.strike else leg2
                    short_leg = leg2 if leg1.strike < leg2.strike else leg1
                    net_debit = round(long_leg.mid - short_leg.mid, 2)
                    width = short_leg.strike - long_leg.strike
                    if net_debit <= 0 or net_debit >= width:
                        continue
                    metrics = calculate_bull_call_spread_metrics(long_leg.strike, short_leg.strike, net_debit)
                else:
                    long_leg = leg1 if leg1.strike > leg2.strike else leg2
                    short_leg = leg2 if leg1.strike > leg2.strike else leg1
                    net_debit = round(long_leg.mid - short_leg.mid, 2)
                    width = long_leg.strike - short_leg.strike
                    if net_debit <= 0 or net_debit >= width:
                        continue
                    metrics = calculate_bear_put_spread_metrics(long_leg.strike, short_leg.strike, net_debit)
                max_profit = metrics["max_profit"]
                max_loss = metrics["max_loss"]
                breakeven = metrics["breakeven"]
                net_premium = abs(net_debit)
                premium_type = "debit"
                multiplier = leg_multiplier
            else:
                net_premium = abs(premium)
                premium_type = "debit"
                max_profit = "Unlimited" if main_contract.right == "C" else f"${(strike - premium) * multiplier:.2f} (cap at strike zero)"
                max_loss = f"${premium * multiplier:.2f} (premium debit paid)"
                breakeven = round(strike + premium if main_contract.right == "C" else strike - premium, 2)

            # Evaluate Eligibility
            eligible, eligibility_reason = evaluate_strategy_eligibility(
                strategy_name=strat_name,
                strike=strike,
                underlying_price=position.market_price,
                quantity_held=position.quantity,
                cash_available=cash_available,
                account_type=account_type,
                contract_multiplier=multiplier,
                contract_currency=contract_currency,
                account_currency=account_currency,
                fx_rate_to_account=fx_rate,
            )
            
            validated_strategies.append({
                "name": strat_name,
                "type": strat.get("type", "income"),
                "expiration": main_contract.expiration.isoformat(),
                "strikes": strat.get("selected_strikes", f"{main_contract.right} at ${strike:.2f}"),
                "net_premium": net_premium,
                "premium_type": premium_type,
                "net_credit_debit": net_premium if premium_type == "credit" else -net_premium,
                "max_profit": max_profit,
                "max_loss": max_loss,
                "breakeven": breakeven,
                "probability_of_profit": (main_contract.open_interest % 25 + 50) if is_demo else None,
                "rationale": strat.get("rationale", ""),
                "eligible": eligible,
                "eligibility_reason": eligibility_reason
            })

        from app.schemas.domain import utc_now
        from app.services.options.chain_provider import atm_implied_volatility

        warnings = []
        if is_demo:
            warnings.append("Simulated data — not suitable for trading decisions.")
        elif live_chain_unavailable:
            warnings.append("Live options chain unavailable; IV percentile and probability of profit are withheld.")
        else:
            warnings.append("Live options chain quotes sourced from market data; verify before trading.")

        atm_iv = atm_implied_volatility(chain, position.market_price)
        atm_contract = min(chain, key=lambda item: abs(item.strike - position.market_price)) if chain else None
        implied_move = None
        implied_move_horizon_days = None
        iv_pct = None
        quantlib_check = None
        if not is_demo and atm_iv is not None and atm_contract is not None:
            days = max((atm_contract.expiration - date.today()).days, 1)
            time_to_expiry = days / 365.0
            implied_move = round(atm_iv * math.sqrt(time_to_expiry) * 100.0, 2)
            implied_move_horizon_days = days
            from app.db.iv_observation_repo import append_iv_history_json, iv_percentile
            from app.services.options.quantlib_benchmark import compare_with_internal_bs

            append_iv_history_json(
                position.symbol,
                atm_iv,
                source=chain_source,
                option_right=atm_contract.right,
                days_to_expiry=days,
                delta=atm_contract.delta,
                moneyness=round(position.market_price / atm_contract.strike, 4) if atm_contract.strike else None,
            )
            iv_pct = iv_percentile(
                position.symbol,
                atm_iv,
                option_right=atm_contract.right,
                days_to_expiry=days,
            )
            quantlib_check = compare_with_internal_bs(
                spot=position.market_price,
                strike=atm_contract.strike,
                days_to_expiry=days,
                risk_free_rate=0.045,
                volatility=atm_iv,
                right=atm_contract.right,
            )
        return {
            "symbol": position.symbol,
            "stock_price": position.market_price,
            "implied_volatility": 0.30 if is_demo else atm_iv,
            "iv_percentile": 50 if is_demo else iv_pct,
            "implied_move_percent": implied_move if implied_move is not None else (5.0 if is_demo else None),
            "implied_move_horizon_days": implied_move_horizon_days,
            "strategies": validated_strategies,
            "market_sentiment": report.get("market_sentiment", "Educational market analysis active."),
            "human_review_required": True,
            "disclaimer": report.get("disclaimer", "Disclaimer: This options analysis is for educational purposes only."),
            "provider": f"gemini:{gemini.model}",
            "asOf": utc_now().isoformat(),
            "dataSource": "Mock" if is_demo else (chain_source if not live_chain_unavailable else "Unavailable"),
            "isMock": is_demo,
            "quoteDelaySeconds": None if is_demo else None,
            "warnings": warnings,
            "provenance": {
                "live_portfolio_data": is_live_portfolio,
                "live_market_data": is_live_market,
                "cached_data": False,
                "mock_fallback_data": is_mock_fallback,
                "web_grounded_context": gemini.last_grounding_used,
                "options_chain_source": chain_source if not is_demo else "Mock",
                "quantlib_benchmark": quantlib_check,
            }
        }
    except Exception as exc:
        if not is_demo:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "OPTIONS_ANALYSIS_UNAVAILABLE",
                    "message": str(exc),
                },
            ) from exc
        if not settings.allow_mock_options_strategy:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=503,
                detail=f"Options strategy generation failed in production: {exc}",
            ) from exc
        return _fallback_options_report(position.symbol, position.market_price, f"Gemini error: {exc}", is_live_portfolio, is_live_market, is_mock_fallback)


def _fallback_options_report(symbol: str, price: float, error_msg: str, is_live_portfolio: bool, is_live_market: bool, is_mock_fallback: bool) -> dict[str, Any]:
    from datetime import date, timedelta

    from app.schemas.domain import utc_now
    expiry = date.today() + timedelta(days=30)
    strike = round(price / 5.0) * 5.0 if price > 0 else 100.0
    premium = round(price * 0.02, 2) if price > 0 else 2.50
    return {
        "symbol": symbol.upper(),
        "stock_price": price,
        "implied_volatility": 0.30 if is_mock_fallback else None,
        "iv_percentile": 50 if is_mock_fallback else None,
        "implied_move_percent": 5.0 if is_mock_fallback else None,
        "strategies": [
            {
                "name": "Covered Call (Educational Candidate)",
                "type": "income",
                "expiration": expiry.isoformat(),
                "strikes": f"Sell ${strike:.2f} Call",
                "net_credit_debit": premium,
                "max_profit": f"${premium * 100:.2f} (premium) + ${(strike - price) * 100:.2f} (upside cap)" if strike > price else f"${premium * 100:.2f}",
                "max_loss": f"${(price - premium) * 100:.2f} (stock drops to zero)",
                "breakeven": round(price - premium, 2),
                "probability_of_profit": 68 if is_mock_fallback else None,
                "rationale": f"Simulated Covered Call strategy candidate due to live API fallback: {error_msg}.",
                "eligible": False,
                "eligibility_reason": "Ineligible for Covered Call: You own 0 shares. (minimum 100 shares required)"
            }
        ],
        "market_sentiment": f"System active in fallback mode. Status: {error_msg}",
        "human_review_required": True,
        "disclaimer": "This options strategy is simulated fallback data. Configure your Gemini API key to enable live options strategy generation.",
        "provider": "deterministic_fallback",
        "asOf": utc_now().isoformat(),
        "dataSource": "Mock",
        "isMock": True,
        "quoteDelaySeconds": 15,
        "warnings": ["Simulated data — not suitable for trading decisions.", f"Fallback active: {error_msg}"],
        "provenance": {
            "live_portfolio_data": is_live_portfolio,
            "live_market_data": False,
            "cached_data": False,
            "mock_fallback_data": True,
            "web_grounded_context": False
        }
    }


