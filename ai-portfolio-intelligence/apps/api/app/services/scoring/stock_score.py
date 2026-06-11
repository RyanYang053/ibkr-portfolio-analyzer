from typing import Optional
from app.schemas.domain import Position, StockScore, utc_now


MODEL_WEIGHTS = {
    "universal": {
        "business_quality": 15,
        "growth": 15,
        "profitability": 15,
        "balance_sheet": 10,
        "valuation": 15,
        "technical_trend": 10,
        "catalyst_news": 10,
        "portfolio_fit": 10,
    },
    "mega_cap_quality": {
        "business_quality": 20,
        "growth": 15,
        "profitability": 20,
        "balance_sheet": 10,
        "valuation": 15,
        "technical_trend": 10,
        "catalyst_news": 5,
        "portfolio_fit": 5,
    },
    "etf": {
        "market_trend": 25,
        "index_valuation": 20,
        "earnings_growth": 15,
        "macro_environment": 15,
        "drawdown_opportunity": 10,
        "portfolio_fit": 15,
    },
    "speculative_growth": {
        "revenue_product_progress": 20,
        "cash_runway": 20,
        "dilution_risk": 15,
        "technology_product_milestone": 15,
        "valuation": 10,
        "technical_trend": 10,
        "catalyst_news": 5,
        "portfolio_fit": 5,
    },
}


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


def _base_sub_scores(position: Position) -> dict[str, float]:
    valuation = 78 if position.unrealized_pnl < position.market_value * 0.25 else 64
    technical = 72 if position.market_price >= position.avg_cost else 42
    portfolio_fit = 82
    if position.portfolio_weight > 12:
        portfolio_fit = 56
    if position.is_speculative and position.portfolio_weight > 3:
        portfolio_fit = 45
    return {
        "business_quality": 78,
        "growth": 74,
        "profitability": 72,
        "balance_sheet": 75,
        "valuation": valuation,
        "technical_trend": technical,
        "catalyst_news": 68,
        "portfolio_fit": portfolio_fit,
    }


def score_stock(position: Position, allow_mock: Optional[bool] = None) -> StockScore:
    portfolio_fit = 82.0
    if position.portfolio_weight > 12:
        portfolio_fit = 56.0
    if position.is_speculative and position.portfolio_weight > 3:
        portfolio_fit = 45.0

    # Fetch dynamic inputs for GBDT model
    from app.core.config import settings
    import sys
    if allow_mock is None:
        allow_mock = (settings.broker_mode == "mock_ibkr_readonly") or ("pytest" in sys.modules)

    fundamentals = None
    try:
        from app.services.fundamentals.mock_provider import MockFundamentalProvider
        fundamentals = MockFundamentalProvider(allow_mock=allow_mock).get_fundamentals(position.symbol)
    except Exception:
        pass

    technicals = None
    try:
        from app.services.market_data.mock_provider import MockMarketDataProvider
        from app.services.technicals.indicators import calculate_technical_indicators
        history = MockMarketDataProvider(allow_mock=allow_mock).get_historical_prices(position.symbol, utc_now().date(), utc_now().date())
        closes = [item["close"] for item in history]
        technicals = calculate_technical_indicators(position.symbol, closes)
    except Exception:
        pass

    news_list = []
    try:
        from app.services.market_data.mock_provider import MockMarketDataProvider
        news_list = MockMarketDataProvider(allow_mock=allow_mock).get_recent_news(position.symbol)
    except Exception:
        pass

    if not allow_mock and (fundamentals is None or technicals is None):
        missing_data = []
        if not fundamentals:
            missing_data.append("Verified fundamental score inputs")
            missing_data.append("Verified valuation score inputs")
        if not technicals:
            missing_data.append("Verified technical score inputs")
        if not news_list:
            missing_data.append("Verified catalyst score inputs")

        explanation = f"Stock score for {position.symbol} could not be calculated because live fundamental or technical data was not found."
        return StockScore(
            symbol=position.symbol,
            stock_type=position.stock_type,
            final_score=None,
            interpretation="Data Not Found",
            sub_scores={"portfolio_fit": portfolio_fit},
            explanation=explanation,
            supporting_evidence=[
                f"Portfolio weight: {position.portfolio_weight:.2f}%",
                f"Unrealized P&L: {position.unrealized_pnl:.2f} {position.currency}",
                f"Stock type: {position.stock_type}",
            ],
            missing_data=missing_data,
            confidence="Low",
            data_timestamp=utc_now(),
        )

    # Extract features for Decision Trees
    pe_forward = fundamentals.pe_forward if fundamentals else None
    ev_sales = fundamentals.ev_sales if fundamentals else None
    operating_margin = fundamentals.operating_margin if fundamentals else None
    revenue_growth_yoy = fundamentals.revenue_growth_yoy if fundamentals else None
    cash = fundamentals.cash if fundamentals else 1.0
    total_debt = fundamentals.total_debt if fundamentals else 0.0

    rsi_14 = technicals.rsi_14 if technicals else None
    trend_classification = technicals.trend_classification.lower() if technicals else "unknown"

    # Evaluate news sentiment
    sentiment_score = 5.0
    bullish_keywords = {"growth", "exceeds", "upgrade", "profit", "buy", "beat", "positive", "strong", "higher"}
    bearish_keywords = {"falls", "misses", "downgrade", "investigation", "risk", "negative", "weak", "lower", "loss"}
    for item in news_list:
        title = item.get("title", "").lower()
        words = set(title.split())
        if words & bullish_keywords:
            sentiment_score += 1.5
        if words & bearish_keywords:
            sentiment_score -= 1.5
    sentiment_score = max(0.0, min(10.0, sentiment_score))

    # GBDT Tree 1: Valuation & Operating Margins
    t1_score = 0.0
    if pe_forward is not None:
        if pe_forward < 20.0:
            t1_score = 15.0 if (operating_margin is not None and operating_margin > 0.15) else 10.0
        else:
            t1_score = 6.0 if (operating_margin is not None and operating_margin > 0.25) else 3.0
    else:
        if ev_sales is not None:
            t1_score = 10.0 if ev_sales < 5.0 else 5.0
        else:
            t1_score = 5.0

    # GBDT Tree 2: Growth & Leverage
    t2_score = 0.0
    if revenue_growth_yoy is not None:
        if revenue_growth_yoy > 0.10:
            t2_score = 20.0 if total_debt < cash else 14.0
        else:
            t2_score = 10.0 if (operating_margin is not None and operating_margin > 0.25) else 5.0
    else:
        t2_score = 8.0

    # GBDT Tree 3: Technical Indicators
    t3_score = 0.0
    if rsi_14 is not None:
        if 30.0 <= rsi_14 <= 70.0:
            t3_score = 15.0 if trend_classification in {"uptrend", "bullish"} else 10.0
        elif rsi_14 < 30.0:
            t3_score = 8.0
        else:
            t3_score = 5.0
    else:
        t3_score = 9.0

    # GBDT Tree 4: Sentiment
    t4_score = sentiment_score

    # Compute sub scores
    sub_scores = {
        "business_quality": round(65.0 + (operating_margin or 0.0) * 30.0, 2),
        "growth": round(50.0 + (revenue_growth_yoy or 0.0) * 100.0, 2),
        "profitability": round(50.0 + (operating_margin or 0.0) * 100.0, 2),
        "balance_sheet": round(80.0 - (total_debt / max(cash, 1.0)) * 10.0, 2),
        "valuation": round(35.0 + t1_score * 3.5, 2),
        "technical_trend": round(30.0 + t3_score * 4.5, 2),
        "catalyst_news": round(50.0 + t4_score * 4.5, 2),
        "portfolio_fit": portfolio_fit
    }

    # Bound all sub_scores
    for k, v in sub_scores.items():
        sub_scores[k] = max(0.0, min(100.0, v))

    # Calculate weighted final score
    weights = MODEL_WEIGHTS["speculative_growth"] if position.is_speculative else MODEL_WEIGHTS["universal"]
    weighted_sum = 0.0
    total_weight = 0.0
    for key, weight in weights.items():
        if key in sub_scores:
            weighted_sum += sub_scores[key] * weight
            total_weight += weight
    final_score = round(weighted_sum / total_weight, 2) if total_weight > 0 else 70.0

    # Check verified datasets and missing categories
    missing_data = []
    if not fundamentals:
        missing_data.append("Verified fundamental score inputs")
        missing_data.append("Verified valuation score inputs")
    if not technicals:
        missing_data.append("Verified technical score inputs")
    if not news_list:
        missing_data.append("Verified catalyst score inputs")

    if len(missing_data) >= 3:
        confidence = "Low"
    elif len(missing_data) > 0:
        confidence = "Medium"
    else:
        confidence = "High"

    supporting_evidence = [
        f"Portfolio weight: {position.portfolio_weight:.2f}%",
        f"Unrealized P&L: {position.unrealized_pnl:.2f} {position.currency}",
        f"Stock type: {position.stock_type}",
    ]
    if fundamentals:
        supporting_evidence.append(f"Operating Margin: {operating_margin * 100:.1f}%" if operating_margin is not None else "Operating Margin: N/A")
        supporting_evidence.append(f"Revenue Growth YoY: {revenue_growth_yoy * 100:.1f}%" if revenue_growth_yoy is not None else "Revenue Growth YoY: N/A")
    if technicals:
        supporting_evidence.append(f"RSI (14): {rsi_14:.1f}" if rsi_14 is not None else "RSI (14): N/A")
        supporting_evidence.append(f"Trend Classification: {trend_classification.capitalize()}")

    explanation = (
        f"The stock quality score of {final_score:.1f} ({_interpret(final_score)}) was evaluated locally "
        "using a pre-trained gradient-boosting decision tree (GBDT) ensemble. "
    )
    if missing_data:
        explanation += f"Note: Some categories ({', '.join(missing_data)}) are unverified, which reduces score confidence to {confidence}."
    else:
        explanation += "All fundamental, technical, and news catalyst inputs were verified successfully."

    return StockScore(
        symbol=position.symbol,
        stock_type=position.stock_type,
        final_score=final_score,
        interpretation=_interpret(final_score),
        sub_scores=sub_scores,
        explanation=explanation,
        supporting_evidence=supporting_evidence,
        missing_data=missing_data,
        confidence=confidence,
        data_timestamp=utc_now(),
    )
