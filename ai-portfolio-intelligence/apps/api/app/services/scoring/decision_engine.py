from __future__ import annotations

from app.schemas.domain import Position, Provenance, Recommendation
from app.services.scoring.stock_score import score_stock


def _action_for(score: float, position: Position) -> str:
    absolute_weight = abs(position.portfolio_weight)
    if position.is_speculative and absolute_weight > 3.0:
        return "Trim Review"
    if score >= 85.0 and absolute_weight < 8.0:
        return "Strong Add"
    if score >= 70.0 and absolute_weight < 10.0:
        return "Add"
    if score >= 62.0:
        return "Hold"
    if score >= 50.0:
        return "Watch"
    if score >= 40.0:
        return "Exit Review"
    return "Avoid"


def build_recommendation(position: Position) -> Recommendation:
    score = score_stock(position)
    decision_grade = score.final_score is not None and score.confidence in {"High", "Medium-High"}
    action = _action_for(score.final_score, position) if decision_grade else "Data Insufficient"

    if action == "Data Insufficient":
        explanation = (
            f"{position.symbol} remains Data Insufficient because the research model does not have enough "
            f"verified coverage for a decision category. {score.explanation}"
        )
    else:
        explanation = (
            f"{position.symbol} is categorized as {action} from an auditable weighted-factor score of "
            f"{score.final_score:.1f} with {score.confidence} confidence. The category is decision support "
            "only and must be reviewed against valuation, portfolio constraints, taxes, and current filings."
        )

    missing_lower = " ".join(score.missing_data).lower()
    mock_active = "mock" in missing_lower or "demo" in missing_lower
    provenance = Provenance(
        live_portfolio_data=position.account_id not in {"MOCK-001", "MOCK-002", "WATCHLIST_ONLY", "SYNTHETIC_RESEARCH"},
        live_market_data=not mock_active and "technical" not in missing_lower,
        cached_data=False,
        mock_fallback_data=mock_active,
        web_grounded_context=False,
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
            "market_data": "present in model" if "technical" not in missing_lower else "missing or stale",
            "fundamentals": "present in model" if "fundamental" not in missing_lower else "missing or stale",
        },
        provenance=provenance,
    )
