"""Score interpretation engine — evidence only, never authoritative outcomes."""

from __future__ import annotations

from app.core.config import settings
from app.core.product_contract import ScoreInterpretation
from app.schemas.domain import Position, Provenance, Recommendation
from app.services.fundamentals.sector_models import resolve_scoring_model
from app.services.scoring.calibration import get_calibration_status
from app.services.scoring.stock_score import score_stock

# Human-readable labels kept for API compatibility; these are NOT decision outcomes.
_SCORE_LABELS: dict[ScoreInterpretation, str] = {
    ScoreInterpretation.HIGH_HEURISTIC_SCORE: "High heuristic score",
    ScoreInterpretation.SUPPORTIVE_SCORE: "Supportive score",
    ScoreInterpretation.MIXED_SCORE: "Mixed score",
    ScoreInterpretation.WEAK_SCORE: "Weak score",
    ScoreInterpretation.HIGH_RISK_SCORE: "High risk score",
    ScoreInterpretation.DATA_INSUFFICIENT: "Data Insufficient",
}


def _interpret_score(score: float, position: Position) -> ScoreInterpretation:
    absolute_weight = abs(position.portfolio_weight)
    if position.is_speculative and absolute_weight > 3.0:
        return ScoreInterpretation.HIGH_RISK_SCORE
    if score >= 85.0:
        model_name = resolve_scoring_model(position)
        if (
            settings.enable_strong_add_recommendations
            and get_calibration_status(model_name) == "sufficient"
        ):
            return ScoreInterpretation.HIGH_HEURISTIC_SCORE
        return ScoreInterpretation.HIGH_HEURISTIC_SCORE
    if score >= 70.0:
        return ScoreInterpretation.SUPPORTIVE_SCORE
    if score >= 55.0:
        return ScoreInterpretation.MIXED_SCORE
    if score >= 40.0:
        return ScoreInterpretation.WEAK_SCORE
    return ScoreInterpretation.WEAK_SCORE


def build_recommendation(position: Position) -> Recommendation:
    """Build a score interpretation. Does not produce Decision Center outcomes."""
    score = score_stock(position)
    decision_grade = score.final_score is not None and score.confidence in {"High", "Medium-High"}
    interpretation = (
        _interpret_score(score.final_score, position)
        if decision_grade
        else ScoreInterpretation.DATA_INSUFFICIENT
    )
    action_label = _SCORE_LABELS[interpretation]

    if interpretation == ScoreInterpretation.DATA_INSUFFICIENT:
        explanation = (
            f"{position.symbol} remains Data Insufficient because the research model does not have enough "
            f"verified coverage for a score interpretation. {score.explanation} "
            "This is analytical evidence only; the Decision Center produces the authoritative outcome."
        )
    else:
        explanation = (
            f"{position.symbol} has score interpretation '{action_label}' from an auditable weighted-factor "
            f"score of {score.final_score:.1f} with {score.confidence} confidence. This is experimental "
            "heuristic evidence only and is not an authoritative Decision Center outcome."
        )

    missing_lower = " ".join(score.missing_data).lower()
    mock_active = "mock" in missing_lower or "demo" in missing_lower
    provenance = Provenance(
        live_portfolio_data=position.account_id
        not in {"MOCK-001", "MOCK-002", "WATCHLIST_ONLY", "SYNTHETIC_RESEARCH"},
        live_market_data=not mock_active and "technical" not in missing_lower,
        cached_data=False,
        mock_fallback_data=mock_active,
        web_grounded_context=False,
    )

    return Recommendation(
        symbol=position.symbol,
        con_id=position.con_id,
        action=action_label,  # type: ignore[arg-type]
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


def score_interpretation_payload(position: Position) -> dict:
    """Explicit evidence payload with deprecated recommendation compatibility."""
    rec = build_recommendation(position)
    return {
        "symbol": rec.symbol,
        "con_id": rec.con_id,
        "score_interpretation": rec.action,
        "score": rec.score,
        "confidence": rec.confidence,
        "explanation": rec.explanation,
        "evidence": rec.evidence,
        "data_freshness": rec.data_freshness,
        "provenance": rec.provenance.model_dump() if hasattr(rec.provenance, "model_dump") else rec.provenance,
        "deprecated": True,
        "authoritative": False,
        "note": "Score interpretation is evidence only. Use Decision Center for authoritative outcomes.",
        # Compatibility shim — never treat as authoritative.
        "action": rec.action,
        "recommendation": rec.model_dump(),
    }
