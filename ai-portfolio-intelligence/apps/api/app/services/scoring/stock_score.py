from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from statistics import fmean
from typing import Optional

from app.schemas.domain import Position, StockScore, utc_now

SCORE_MODEL_VERSION = "2026.07.1"


MODEL_WEIGHTS: dict[str, dict[str, float]] = {
    "universal": {
        "business_quality": 18,
        "growth": 15,
        "profitability": 17,
        "balance_sheet": 12,
        "valuation": 15,
        "technical_trend": 10,
        "catalyst_news": 5,
        "portfolio_fit": 8,
    },
    "mega_cap_quality": {
        "business_quality": 22,
        "growth": 14,
        "profitability": 20,
        "balance_sheet": 12,
        "valuation": 15,
        "technical_trend": 8,
        "catalyst_news": 3,
        "portfolio_fit": 6,
    },
    "speculative_growth": {
        "business_quality": 8,
        "growth": 22,
        "profitability": 10,
        "balance_sheet": 20,
        "valuation": 10,
        "technical_trend": 12,
        "catalyst_news": 8,
        "portfolio_fit": 10,
    },
    "etf": {
        "market_trend": 35,
        "drawdown_opportunity": 20,
        "valuation": 10,
        "catalyst_news": 5,
        "portfolio_fit": 30,
    },
    "technology_heuristic": {
        "business_quality": 16,
        "growth": 20,
        "profitability": 14,
        "balance_sheet": 10,
        "valuation": 14,
        "technical_trend": 12,
        "catalyst_news": 6,
        "portfolio_fit": 8,
    },
    "financials_heuristic": {
        "business_quality": 14,
        "growth": 10,
        "profitability": 22,
        "balance_sheet": 20,
        "valuation": 18,
        "technical_trend": 8,
        "catalyst_news": 3,
        "portfolio_fit": 5,
    },
    "reit_heuristic": {
        "business_quality": 12,
        "growth": 8,
        "profitability": 20,
        "balance_sheet": 18,
        "valuation": 22,
        "technical_trend": 8,
        "catalyst_news": 4,
        "portfolio_fit": 8,
    },
    "utilities_heuristic": {
        "business_quality": 16,
        "growth": 6,
        "profitability": 22,
        "balance_sheet": 16,
        "valuation": 18,
        "technical_trend": 8,
        "catalyst_news": 4,
        "portfolio_fit": 10,
    },
    "consumer_cyclical_heuristic": {
        "business_quality": 16,
        "growth": 16,
        "profitability": 16,
        "balance_sheet": 12,
        "valuation": 16,
        "technical_trend": 10,
        "catalyst_news": 6,
        "portfolio_fit": 8,
    },
    "consumer_defensive_heuristic": {
        "business_quality": 20,
        "growth": 10,
        "profitability": 20,
        "balance_sheet": 14,
        "valuation": 16,
        "technical_trend": 8,
        "catalyst_news": 4,
        "portfolio_fit": 8,
    },
    "communication_services_heuristic": {
        "business_quality": 16,
        "growth": 16,
        "profitability": 16,
        "balance_sheet": 10,
        "valuation": 16,
        "technical_trend": 12,
        "catalyst_news": 6,
        "portfolio_fit": 8,
    },
    "healthcare_heuristic": {
        "business_quality": 16,
        "growth": 18,
        "profitability": 14,
        "balance_sheet": 12,
        "valuation": 14,
        "technical_trend": 10,
        "catalyst_news": 8,
        "portfolio_fit": 8,
    },
    "energy_heuristic": {
        "business_quality": 12,
        "growth": 12,
        "profitability": 20,
        "balance_sheet": 14,
        "valuation": 18,
        "technical_trend": 10,
        "catalyst_news": 6,
        "portfolio_fit": 8,
    },
    "industrials_heuristic": {
        "business_quality": 16,
        "growth": 12,
        "profitability": 18,
        "balance_sheet": 14,
        "valuation": 16,
        "technical_trend": 10,
        "catalyst_news": 6,
        "portfolio_fit": 8,
    },
    "materials_heuristic": {
        "business_quality": 12,
        "growth": 12,
        "profitability": 18,
        "balance_sheet": 14,
        "valuation": 18,
        "technical_trend": 10,
        "catalyst_news": 6,
        "portfolio_fit": 10,
    },
    "diversified_heuristic": {
        "business_quality": 14,
        "growth": 10,
        "profitability": 14,
        "balance_sheet": 12,
        "valuation": 14,
        "technical_trend": 10,
        "catalyst_news": 6,
        "portfolio_fit": 30,
    },
}


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


def _linear(value: float, low: float, high: float) -> float:
    if high <= low:
        raise ValueError("high must be greater than low")
    return _clamp((value - low) / (high - low) * 100.0)


def _average(values: list[float]) -> float | None:
    return fmean(values) if values else None


def _interpret(score: float) -> str:
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 55:
        return "Mixed"
    if score >= 40:
        return "Weak"
    return "Broken/high-risk"


def _portfolio_fit(position: Position) -> float:
    score = 90.0
    absolute_weight = abs(position.portfolio_weight)
    if absolute_weight > 8.0:
        score -= min(35.0, (absolute_weight - 8.0) * 4.0)
    if position.is_speculative and absolute_weight > 3.0:
        score -= min(35.0, (absolute_weight - 3.0) * 8.0)
    return _clamp(score)


def _news_score(news_list: list[dict]) -> tuple[float | None, list[str]]:
    if not news_list:
        return None, []

    bullish = {"beat", "beats", "upgrade", "upgraded", "profit", "profitable", "growth", "approval", "contract"}
    bearish = {"miss", "misses", "downgrade", "downgraded", "investigation", "fraud", "dilution", "loss", "warning"}
    score = 50.0
    evidence: list[str] = []
    for item in news_list[:10]:
        title = str(item.get("title", ""))
        words = set(re.findall(r"[a-z]+", title.lower()))
        positive_hits = words & bullish
        negative_hits = words & bearish
        score += 4.0 * len(positive_hits)
        score -= 5.0 * len(negative_hits)
        if positive_hits or negative_hits:
            evidence.append(title)
    return _clamp(score), evidence[:3]


def _technical_score(technicals) -> float:
    trend_scores = {
        "strong uptrend": 90.0,
        "uptrend": 75.0,
        "neutral": 55.0,
        "weakening": 40.0,
        "downtrend": 25.0,
        "strong downtrend": 10.0,
    }
    trend = trend_scores.get(technicals.trend_classification.lower(), 50.0)
    rsi = technicals.rsi_14
    if 40.0 <= rsi <= 65.0:
        momentum = 75.0
    elif 30.0 <= rsi < 40.0 or 65.0 < rsi <= 75.0:
        momentum = 55.0
    elif rsi < 30.0:
        momentum = 45.0
    else:
        momentum = 30.0
    macd = 65.0 if technicals.macd_histogram > 0 else 35.0 if technicals.macd_histogram < 0 else 50.0
    return fmean([trend, momentum, macd])


def _stock_fundamental_scores(fundamentals) -> dict[str, float]:
    scores: dict[str, float] = {}

    quality_parts = [
        _linear(fundamentals.gross_margin, 0.15, 0.75),
        _linear(fundamentals.operating_margin, -0.10, 0.35),
    ]
    scores["business_quality"] = fmean(quality_parts)
    scores["growth"] = _linear(fundamentals.revenue_growth_yoy, -0.10, 0.35)

    profitability_parts = [_linear(fundamentals.operating_margin, -0.15, 0.35)]
    if fundamentals.fcf_yield is not None:
        profitability_parts.append(_linear(fundamentals.fcf_yield, -0.03, 0.08))
    elif fundamentals.free_cash_flow != 0:
        profitability_parts.append(75.0 if fundamentals.free_cash_flow > 0 else 15.0)
    scores["profitability"] = fmean(profitability_parts)

    capital = abs(fundamentals.cash) + abs(fundamentals.total_debt)
    if capital > 0:
        net_cash_ratio = (fundamentals.cash - fundamentals.total_debt) / capital
        scores["balance_sheet"] = _clamp(50.0 + 50.0 * net_cash_ratio)

    valuation_parts: list[float] = []
    if fundamentals.pe_forward is not None and fundamentals.pe_forward > 0:
        valuation_parts.append(_clamp(110.0 - fundamentals.pe_forward * 2.5))
    if fundamentals.ev_sales is not None and fundamentals.ev_sales >= 0:
        valuation_parts.append(_clamp(105.0 - fundamentals.ev_sales * 5.0))
    if fundamentals.fcf_yield is not None:
        valuation_parts.append(_linear(fundamentals.fcf_yield, -0.02, 0.08))
    valuation = _average(valuation_parts)
    if valuation is not None:
        scores["valuation"] = valuation

    return scores


def _weighted_score(sub_scores: dict[str, float], weights: dict[str, float]) -> tuple[float | None, float]:
    total_model_weight = sum(weights.values())
    available_weight = sum(weight for factor, weight in weights.items() if factor in sub_scores)
    if available_weight <= 0 or total_model_weight <= 0:
        return None, 0.0
    score = sum(sub_scores[factor] * weights[factor] for factor in sub_scores if factor in weights) / available_weight
    return _clamp(score), available_weight / total_model_weight


def score_stock(position: Position, allow_mock: Optional[bool] = None) -> StockScore:
    from app.core.config import settings

    if allow_mock is None:
        allow_mock = settings.broker_mode == "mock_ibkr_readonly" or "pytest" in sys.modules

    fundamentals = None
    technicals = None
    news_list: list[dict] = []
    history_source = "missing"

    try:
        from app.services.fundamentals.mock_provider import MockFundamentalProvider
        from app.services.fundamentals.snapshot_store import get_point_in_time_fundamentals

        if allow_mock:
            fundamentals = MockFundamentalProvider(allow_mock=True).get_fundamentals(position.symbol)
        else:
            fundamentals = get_point_in_time_fundamentals(
                position.symbol,
                utc_now().date(),
                allow_synthetic_demo=False,
            )
            if fundamentals is None:
                fundamentals = MockFundamentalProvider(allow_mock=False).get_fundamentals(position.symbol)
    except Exception:
        fundamentals = None

    try:
        from app.services.market_data.mock_provider import MockMarketDataProvider
        from app.services.technicals.indicators import calculate_technical_indicators

        today = utc_now().date()
        history = MockMarketDataProvider(allow_mock=allow_mock).get_historical_prices(
            position.symbol,
            today - timedelta(days=400),
            today,
        )
        closes = [float(item["close"]) for item in history]
        history_source = str(history[-1].get("source", "unknown")) if history else "missing"
        technicals = calculate_technical_indicators(position.symbol, closes)
    except Exception:
        technicals = None

    try:
        from app.services.market_data.news_service import fetch_scoring_news

        news_list = fetch_scoring_news(position.symbol, allow_mock=allow_mock)
    except Exception:
        news_list = []

    sub_scores: dict[str, float] = {"portfolio_fit": _portfolio_fit(position)}
    evidence = [
        f"Portfolio weight: {position.portfolio_weight:.2f}%",
        f"Unrealized P&L: {position.unrealized_pnl:.2f} {position.currency}",
        f"Security classification: {position.stock_type}",
    ]
    missing_data: list[str] = []

    if position.is_etf:
        model_name = "etf"
        if technicals is not None:
            sub_scores["market_trend"] = _technical_score(technicals)
            sub_scores["drawdown_opportunity"] = _clamp(-technicals.drawdown_from_52w_high * 4.0)
            evidence.extend(
                [
                    f"RSI (14): {technicals.rsi_14:.2f}",
                    f"Trend: {technicals.trend_classification}",
                    f"Drawdown from 52-week high: {technicals.drawdown_from_52w_high:.2f}%",
                ]
            )
        else:
            missing_data.append("Verified ETF price history")
        # The current provider does not supply index-level earnings yield, holdings
        # valuation, expense ratio, tracking error, or liquidity metrics.
        missing_data.append("ETF valuation and implementation metrics")
    else:
        from app.services.fundamentals.sector_models import resolve_scoring_model, score_fundamentals_for_sector

        model_name = resolve_scoring_model(position)
        if fundamentals is not None and not str(fundamentals.source).endswith("_etf"):
            sub_scores.update(score_fundamentals_for_sector(fundamentals, position.sector or "Unknown"))
            evidence.extend(
                [
                    f"Revenue growth YoY: {fundamentals.revenue_growth_yoy * 100:.2f}%",
                    f"Operating margin: {fundamentals.operating_margin * 100:.2f}%",
                    f"Fundamental source: {fundamentals.source}",
                    f"Fundamental report date: {fundamentals.report_date.isoformat()}",
                ]
            )
            if (date.today() - fundamentals.report_date).days > 180:
                missing_data.append("Fresh fundamental filing data")
        else:
            missing_data.extend(["Verified fundamental inputs", "Verified valuation inputs"])

        if technicals is not None:
            sub_scores["technical_trend"] = _technical_score(technicals)
            evidence.extend(
                [
                    f"RSI (14): {technicals.rsi_14:.2f}",
                    f"MACD histogram: {technicals.macd_histogram:.4f}",
                    f"Trend: {technicals.trend_classification}",
                ]
            )
        else:
            missing_data.append("Verified technical inputs")

    catalyst_score, catalyst_evidence = _news_score(news_list)
    if catalyst_score is not None:
        sub_scores["catalyst_news"] = catalyst_score
        evidence.extend(f"News signal: {headline}" for headline in catalyst_evidence)
    else:
        missing_data.append("Recent catalyst/news inputs")

    weights = MODEL_WEIGHTS.get(model_name, MODEL_WEIGHTS["universal"])
    raw_score, coverage = _weighted_score(sub_scores, weights)

    input_sources = {
        str(getattr(fundamentals, "source", "missing")),
        history_source,
        *(str(item.get("source", "missing")) for item in news_list),
    }
    uses_mock = any(source.startswith("mock") for source in input_sources)
    if uses_mock:
        missing_data.append("Live inputs (demo/mock data is active)")

    # Do not emit a composite score when less than 60% of the model is supported.
    final_score = round(raw_score, 2) if raw_score is not None and coverage >= 0.60 else None
    missing_data = list(dict.fromkeys(missing_data))

    if final_score is None:
        confidence = "Low"
        interpretation = "Data Not Found"
    elif uses_mock:
        confidence = "Medium"
        interpretation = _interpret(final_score)
    elif coverage >= 0.90 and not missing_data:
        confidence = "High"
        interpretation = _interpret(final_score)
    elif coverage >= 0.75:
        confidence = "Medium-High"
        interpretation = _interpret(final_score)
    elif coverage >= 0.60:
        confidence = "Medium"
        interpretation = _interpret(final_score)
    else:
        confidence = "Low"
        interpretation = "Data Not Found"

    rounded_sub_scores = {key: round(value, 2) for key, value in sub_scores.items()}
    if final_score is None:
        explanation = (
            f"No composite score is produced for {position.symbol}: only {coverage * 100:.1f}% of the "
            "declared model weight has usable inputs. A minimum of 60% is required."
        )
    else:
        explanation = (
            f"{position.symbol} received a deterministic weighted-factor score of {final_score:.1f} "
            f"({_interpret(final_score)}), with {coverage * 100:.1f}% model coverage. "
            "This is an auditable rule-based model, not a trained machine-learning model and not a forecast of returns."
        )
        if missing_data:
            explanation += f" Confidence is limited by: {', '.join(missing_data)}."

    evidence.append(f"Model coverage: {coverage * 100:.1f}%")

    if final_score is not None:
        import hashlib
        import json

        from app.services.scoring.calibration_ingestion import (
            materialize_calibration_observations,
            record_score_observation,
        )

        input_sources: list[str] = []
        if fundamentals is not None:
            input_sources.append(str(fundamentals.source))
        if technicals is not None:
            input_sources.append(history_source)
        if news_list:
            input_sources.append("news_live" if not allow_mock else "news_mock")
            for item in news_list:
                input_sources.append(str(item.get("source", "news")))
        elif not allow_mock:
            input_sources.append("news_unavailable_live")
        feature_snapshot_hash = hashlib.sha256(
            json.dumps(
                {
                    "model_name": model_name,
                    "model_version": SCORE_MODEL_VERSION,
                    "sub_scores": rounded_sub_scores,
                    "missing_data": sorted(missing_data),
                    "input_sources": sorted(input_sources),
                },
                sort_keys=True,
            ).encode("utf-8"),
        ).hexdigest()[:16]

        record_score_observation(
            symbol=position.symbol,
            model_name=model_name,
            score=final_score,
            model_version=SCORE_MODEL_VERSION,
            feature_snapshot_hash=feature_snapshot_hash,
            input_sources=input_sources,
            synthetic_demo=uses_mock or bool(allow_mock),
        )
        materialize_calibration_observations(model_name, allow_mock=uses_mock or bool(allow_mock))

    return StockScore(
        symbol=position.symbol,
        stock_type=position.stock_type,
        final_score=final_score,
        interpretation=interpretation,
        sub_scores=rounded_sub_scores,
        explanation=explanation,
        supporting_evidence=evidence,
        missing_data=missing_data,
        confidence=confidence,
        data_timestamp=utc_now(),
    )
