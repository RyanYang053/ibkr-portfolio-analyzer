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
    inputs_verified = not score.missing_data
    action = _action_for(score.final_score, position) if inputs_verified and score.final_score is not None else "Data Insufficient"

    explanation = (
        f"{position.symbol} is categorized as {action}. The current score is a placeholder "
        "heuristic and cannot support an add, trim, or exit category until live fundamental, "
        "technical, valuation, and catalyst inputs are verified."
    )
    return Recommendation(
        symbol=position.symbol,
        action=action,  # type: ignore[arg-type]
        score=score.final_score,
        confidence=score.confidence,
        add_zone=None,
        hold_zone=None,
        trim_review_zone=None,
        exit_review_trigger=None,
        explanation=explanation,
        evidence=score.supporting_evidence,
        data_freshness={
            "portfolio": position.updated_at.isoformat(),
            "score": score.data_timestamp.isoformat(),
            "market_data": "unverified",
            "fundamentals": "unverified",
        },
    )
