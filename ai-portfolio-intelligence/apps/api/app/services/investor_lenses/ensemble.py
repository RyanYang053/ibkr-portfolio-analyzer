from __future__ import annotations

from app.services.investor_lenses import (
    bogle_discipline,
    buffett_quality,
    factor_quality,
    graham_piotroski,
    greenblatt,
    lynch_garp,
    marks_risk,
    munger_inversion,
    regime_balance,
)
from app.services.investor_lenses.base import LensInputs, LensResult


LENS_MODULES = (
    buffett_quality,
    graham_piotroski,
    greenblatt,
    lynch_garp,
    marks_risk,
    regime_balance,
    factor_quality,
    bogle_discipline,
    munger_inversion,
)


def evaluate_all_lenses(inputs: LensInputs) -> list[LensResult]:
    return [module.evaluate(inputs) for module in LENS_MODULES]


def ensemble_synthesis(results: list[LensResult]) -> dict[str, object]:
    """Ordered disagreements + synthesis labels — not a single guru average score."""
    available = [r for r in results if r.status in {"available", "provisional"} and r.score is not None]
    ordered = sorted(available, key=lambda r: (-(r.score or 0.0), r.lens_id))
    disagreements: list[dict[str, object]] = []
    if len(ordered) >= 2:
        top = ordered[0]
        bottom = ordered[-1]
        if (top.score or 0) - (bottom.score or 0) >= 25:
            disagreements.append(
                {
                    "type": "score_spread",
                    "high_lens": top.lens_id,
                    "high_score": top.score,
                    "low_lens": bottom.lens_id,
                    "low_score": bottom.score,
                    "spread": round((top.score or 0) - (bottom.score or 0), 2),
                }
            )
    labels: list[str] = []
    if any(r.lens_id == "marks_risk" and (r.score or 0) < 40 for r in available):
        labels.append("risk_caution")
    if any(r.lens_id == "buffett_quality" and (r.score or 0) >= 70 for r in available):
        labels.append("quality_supportive")
    if any(r.lens_id == "munger_inversion" and (r.score or 0) < 40 for r in available):
        labels.append("inversion_flags")
    if not available:
        labels.append("data_insufficient")
    return {
        "ordered_lenses": [
            {"lens_id": r.lens_id, "score": r.score, "status": r.status} for r in ordered
        ],
        "disagreements": disagreements,
        "synthesis_labels": labels,
        "note": "Ensemble reports disagreements and labels only; it does not average guru scores.",
    }
