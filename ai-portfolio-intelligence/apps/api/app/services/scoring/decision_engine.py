from app.schemas.domain import Position, Recommendation
from app.services.scoring.stock_score import score_stock


def _action_for(score: float, position: Position) -> str:
    if position.is_speculative and position.portfolio_weight > 3:
        return "Trim Review"
    if score >= 85 and position.portfolio_weight < 8:
        return "Strong Add"
    if score >= 70 and position.portfolio_weight < 10:
        return "Add"
    if score >= 62:
        return "Hold"
    if score >= 50:
        return "Watch"
    if score >= 40:
        return "Exit Review"
    return "Avoid"


def build_recommendation(position: Position) -> Recommendation:
    score = score_stock(position)
    action = _action_for(score.final_score, position)
    support_price = position.market_price * 0.92
    resistance_price = position.market_price * 1.18
    exit_price = position.market_price * 0.78

    explanation = (
        f"{position.symbol} is categorized as {action} for decision support based on a "
        f"{score.final_score:.1f} score, {position.portfolio_weight:.2f}% portfolio weight, "
        "and the current mock data set. This suggestion requires independent review."
    )
    return Recommendation(
        symbol=position.symbol,
        action=action,  # type: ignore[arg-type]
        score=score.final_score,
        confidence=score.confidence,
        add_zone=f"Potential add zone near {support_price:.2f} if thesis remains intact.",
        hold_zone=f"Hold review zone around current price {position.market_price:.2f}.",
        trim_review_zone=f"Trim review zone above {resistance_price:.2f} or if concentration exceeds limits.",
        exit_review_trigger=f"Exit review trigger below {exit_price:.2f} or if fundamentals/news invalidate the thesis.",
        explanation=explanation,
        evidence=score.supporting_evidence,
        data_freshness={
            "portfolio": position.updated_at.isoformat(),
            "score": score.data_timestamp.isoformat(),
            "market_data": "mock_current",
            "fundamentals": "mock_snapshot",
        },
    )
