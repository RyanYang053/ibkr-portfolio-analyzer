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


def score_stock(position: Position) -> StockScore:
    portfolio_fit = 82.0
    if position.portfolio_weight > 12:
        portfolio_fit = 56.0
    if position.is_speculative and position.portfolio_weight > 3:
        portfolio_fit = 45.0
    missing_data = [
        "Verified fundamental score inputs",
        "Verified technical score inputs",
        "Verified valuation score inputs",
        "Verified catalyst score inputs",
    ]
    return StockScore(
        symbol=position.symbol,
        stock_type=position.stock_type,
        final_score=None,
        interpretation="Data Insufficient",
        sub_scores={"portfolio_fit": portfolio_fit},
        explanation=(
            "A company-quality score is withheld because the scoring engine does not yet have "
            "verified fundamental, valuation, technical, and catalyst inputs. Portfolio fit is "
            "reported separately and must not be interpreted as a stock-quality score."
        ),
        supporting_evidence=[
            f"Portfolio weight: {position.portfolio_weight:.2f}%",
            f"Unrealized P&L: {position.unrealized_pnl:.2f} {position.currency}",
            f"Stock type: {position.stock_type}",
        ],
        missing_data=missing_data,
        confidence="Low",
        data_timestamp=utc_now(),
    )
