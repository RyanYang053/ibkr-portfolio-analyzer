from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.schemas.domain import Position, utc_now
from app.services.ai.thesis_tracker import evaluate_thesis


CONFIDENCE_ORDER = ["Low", "Medium", "Medium-High", "High"]


def _cap_confidence(current: str, cap: str) -> str:
    if CONFIDENCE_ORDER.index(current) <= CONFIDENCE_ORDER.index(cap):
        return current
    return cap


def _evidence_item(evidence_id: str, category: str, source: str, payload: Any, timestamp: str | None = None) -> dict[str, Any]:
    return {
        "id": evidence_id,
        "category": category,
        "source": source,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }


def build_structured_stock_context(
    *,
    position: Position | None,
    score: Any,
    recommendation: Any,
    technicals: Any,
    fundamentals: Any,
    valuation: dict[str, Any] | None,
    catalysts: list[dict[str, Any]] | None,
    portfolio_timestamp: datetime | None,
) -> dict[str, Any]:
    now = utc_now()
    position_payload = _safe_position_payload(position)
    score_payload = score.model_dump(mode="json") if hasattr(score, "model_dump") else score
    recommendation_payload = recommendation.model_dump(mode="json") if hasattr(recommendation, "model_dump") else recommendation
    technical_payload = technicals.model_dump(mode="json") if hasattr(technicals, "model_dump") else technicals
    fundamental_payload = fundamentals.model_dump(mode="json") if hasattr(fundamentals, "model_dump") else fundamentals

    price_missing = position is None or position.market_price <= 0
    price_timestamp = position.updated_at if position else None
    fundamental_date = getattr(fundamentals, "report_date", None) if fundamentals else None
    technical_date = getattr(technicals, "date", None) if technicals else None
    valuation_missing = valuation is None or not any(
        valuation.get(key) is not None for key in ("pe_forward", "ev_sales", "fcf_yield")
    )
    catalysts_missing = not catalysts
    catalyst_timestamp = _latest_catalyst_timestamp(catalysts)
    categories = {
        "portfolio": {
            "missing": portfolio_timestamp is None,
            "stale": portfolio_timestamp is None or portfolio_timestamp < now - timedelta(hours=36),
            "timestamp": portfolio_timestamp.isoformat() if portfolio_timestamp else None,
        },
        "price": {
            "missing": price_missing,
            "stale": price_timestamp is not None and price_timestamp < now - timedelta(minutes=15),
            "timestamp": position.updated_at.isoformat() if position else None,
        },
        "fundamentals": {
            "missing": fundamentals is None,
            "stale": _date_is_stale(fundamental_date, now, days=120),
            "timestamp": str(fundamental_date) if fundamentals else None,
        },
        "technicals": {
            "missing": technicals is None,
            "stale": _date_is_stale(technical_date, now, days=5),
            "timestamp": str(technical_date) if technicals else None,
        },
        "valuation": {
            "missing": valuation_missing,
            "stale": False,
            "timestamp": now.isoformat() if not valuation_missing else None,
        },
        "catalysts": {
            "missing": catalysts_missing,
            "stale": catalysts_missing or catalyst_timestamp is None or catalyst_timestamp < now - timedelta(days=7),
            "timestamp": catalyst_timestamp.isoformat() if catalyst_timestamp else None,
        },
    }
    missing_count = sum(1 for category in categories.values() if category["missing"])
    scores = {
        "final_score": getattr(score, "final_score", None),
        "technical_score": None if categories["technicals"]["missing"] else _sub_score(score, "technical_trend"),
        "catalyst_score": None if categories["catalysts"]["missing"] else _sub_score(score, "catalyst_news"),
    }
    data_quality = {
        "categories": categories,
        "missing_categories": [name for name, category in categories.items() if category["missing"]],
        "missing_categories_count": missing_count,
        "stale_categories": [name for name, category in categories.items() if category["stale"]],
        "confidence_cap": evaluate_confidence_limits_from_categories(categories)["confidence_cap"],
    }
    thesis = evaluate_thesis(
        position,
        score,
        data_quality,
        current_data={
            "fundamentals": fundamental_payload,
            "technicals": technical_payload,
            "valuation": valuation,
            "catalysts": catalysts,
        },
        user_id="local-dev",
    )
    rule_engine = build_rule_engine_summary(position, score, recommendation, technicals, fundamentals, valuation, data_quality, thesis)
    evidence = [
        _evidence_item("ev_portfolio_position", "portfolio", "broker_adapter_readonly", position_payload, categories["price"]["timestamp"]),
        _evidence_item("ev_stock_score", "scoring_engine", "stock_score", score_payload),
        _evidence_item("ev_recommendation", "decision_support", "decision_engine", recommendation_payload),
        _evidence_item("ev_rule_engine", "rule_engine", "deterministic_rules", rule_engine),
        _evidence_item("ev_technicals", "technical", "technical_indicator_engine", technical_payload, categories["technicals"]["timestamp"]),
        _evidence_item("ev_fundamentals", "fundamental", "fundamental_provider", fundamental_payload, categories["fundamentals"]["timestamp"]),
        _evidence_item("ev_valuation", "valuation", "valuation_view", valuation, categories["valuation"]["timestamp"]),
        _evidence_item("ev_catalysts", "catalyst", "catalyst_provider", catalysts, categories["catalysts"]["timestamp"]),
        _evidence_item("ev_data_quality", "data_quality", "freshness_checker", data_quality),
        _evidence_item("ev_thesis", "thesis", "thesis_tracker", thesis),
    ]
    return {
        "schema_version": "stock_structured_context.v1",
        "structured_data_only": True,
        "symbol": position.symbol if position else None,
        "position": position_payload,
        "score": score_payload,
        "recommendation": recommendation_payload,
        "technical_indicators": technical_payload,
        "fundamentals": fundamental_payload,
        "valuation": valuation,
        "catalysts": catalysts,
        "scores": scores,
        "rule_engine": rule_engine,
        "data_quality": data_quality,
        "thesis": thesis,
        "evidence": evidence,
        "forbidden_context": ["broker_credentials", "order_submission", "trade_execution", "account_passwords"],
    }


def evaluate_confidence_limits(context: dict[str, Any]) -> dict[str, Any]:
    categories = context["data_quality"]["categories"]
    return evaluate_confidence_limits_from_categories(categories)


def evaluate_confidence_limits_from_categories(categories: dict[str, Any]) -> dict[str, Any]:
    confidence_cap = "High"
    add_zone_allowed = True
    action_override = None

    if categories["portfolio"]["stale"]:
        confidence_cap = _cap_confidence(confidence_cap, "Medium")
    if categories["price"]["missing"]:
        add_zone_allowed = False
    if categories["fundamentals"]["missing"]:
        confidence_cap = _cap_confidence(confidence_cap, "Medium")

    missing_count = sum(1 for category in categories.values() if category["missing"])
    if missing_count > 2:
        action_override = "Data Insufficient"
        confidence_cap = _cap_confidence(confidence_cap, "Low")

    return {
        "confidence_cap": confidence_cap,
        "add_zone_allowed": add_zone_allowed,
        "action_override": action_override,
    }


def build_claim(claim_id: str, claim_type: str, text: str, evidence_ids: list[str]) -> dict[str, Any]:
    return {
        "id": claim_id,
        "type": claim_type,
        "text": text,
        "evidence_ids": evidence_ids,
    }


def build_rule_engine_summary(
    position: Position | None,
    score: Any,
    recommendation: Any,
    technicals: Any,
    fundamentals: Any,
    valuation: dict[str, Any] | None,
    data_quality: dict[str, Any],
    thesis: dict[str, Any],
) -> dict[str, Any]:
    technical_flags: list[str] = []
    valuation_flags: list[str] = []
    risk_flags: list[str] = []

    if technicals is not None:
        if getattr(technicals, "trend_classification", "") in {"downtrend", "breakdown", "weakening"}:
            technical_flags.append("technical_trend_weakening")
        if getattr(technicals, "drawdown_from_52w_high", 0) < -20:
            technical_flags.append("large_drawdown_from_52w_high")
        volume_ratio = getattr(technicals, "volume_ratio", None)
        if volume_ratio is not None and volume_ratio > 2:
            technical_flags.append("elevated_volume")
    else:
        technical_flags.append("technical_data_missing")

    if valuation:
        ev_sales = valuation.get("ev_sales")
        fcf_yield = valuation.get("fcf_yield")
        if ev_sales is not None and ev_sales > 15:
            valuation_flags.append("high_ev_sales_multiple")
        if fcf_yield is not None and fcf_yield < 0.02:
            valuation_flags.append("low_free_cash_flow_yield")
    else:
        valuation_flags.append("valuation_data_missing")

    if position is not None:
        if position.portfolio_weight > 15:
            risk_flags.append("high_single_position_concentration")
        if position.is_speculative and position.portfolio_weight > 3:
            risk_flags.append("speculative_position_above_suggested_limit")
    if data_quality["missing_categories_count"] > 2:
        risk_flags.append("major_data_insufficient")

    return {
        "rule_engine_action": getattr(recommendation, "action", None),
        "thesis_status": thesis["status"],
        "technical_red_flags": technical_flags,
        "valuation_red_flags": valuation_flags,
        "risk_flags": risk_flags,
        "data_freshness_status": {
            name: "missing" if category["missing"] else "stale" if category["stale"] else "fresh"
            for name, category in data_quality["categories"].items()
        },
        "missing_data": data_quality["missing_categories"],
    }


def _sub_score(score: Any, key: str) -> float | None:
    if not score:
        return None
    sub_scores = getattr(score, "sub_scores", None)
    if isinstance(sub_scores, dict):
        return sub_scores.get(key)
    if isinstance(score, dict):
        return score.get("sub_scores", {}).get(key)
    return None


def _safe_position_payload(position: Position | None) -> dict[str, Any] | None:
    if position is None:
        return None
    return {
        "symbol": position.symbol,
        "company_name": position.company_name,
        "asset_class": position.asset_class,
        "market_price": position.market_price,
        "market_value": position.market_value,
        "unrealized_pnl": position.unrealized_pnl,
        "realized_pnl": position.realized_pnl,
        "currency": position.currency,
        "sector": position.sector,
        "industry": position.industry,
        "portfolio_weight": position.portfolio_weight,
        "stock_type": position.stock_type,
        "is_etf": position.is_etf,
        "is_speculative": position.is_speculative,
        "updated_at": position.updated_at.isoformat(),
    }


def _date_is_stale(value: Any, now: datetime, *, days: int) -> bool:
    if value is None:
        return False
    if isinstance(value, datetime):
        observed = value
    else:
        try:
            observed = datetime.fromisoformat(str(value))
        except ValueError:
            return True
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    return observed < now - timedelta(days=days)


def _latest_catalyst_timestamp(catalysts: list[dict[str, Any]] | None) -> datetime | None:
    timestamps: list[datetime] = []
    for item in catalysts or []:
        raw = item.get("providerPublishTime")
        if isinstance(raw, (int, float)) and raw > 0:
            timestamps.append(datetime.fromtimestamp(raw, tz=timezone.utc))
    return max(timestamps) if timestamps else None
