from __future__ import annotations

from app.services.investor_lenses.base import LensComponent, LensInputs, LensResult, _clamp, _mean_available, _num

LENS_ID = "factor_quality"
VERSION = "0.1.0"


def evaluate(inputs: LensInputs) -> LensResult:
    f = inputs.factor_exposures
    fund = inputs.fundamentals
    exclusions: list[str] = []
    quality_factor = _num(f, "quality")
    roe = _num(fund, "return_on_equity")
    gross_margin = _num(fund, "gross_margin")

    qf_score = None if quality_factor is None else _clamp(50.0 + quality_factor * 50.0)
    roe_score = None if roe is None else _clamp((roe / 0.15) * 100.0)
    gm_score = None if gross_margin is None else _clamp((gross_margin / 0.40) * 100.0)
    if quality_factor is None:
        exclusions.append("quality_factor_missing")
    if roe is None:
        exclusions.append("roe_missing")
    if gross_margin is None:
        exclusions.append("gross_margin_missing")

    components = (
        LensComponent("quality_factor", qf_score, ("factors.quality",)),
        LensComponent("roe", roe_score, ("fundamentals.return_on_equity",)),
        LensComponent("gross_margin", gm_score, ("fundamentals.gross_margin",)),
    )
    score = _mean_available([qf_score, roe_score, gm_score])
    status = "withheld" if score is None else ("provisional" if exclusions else "available")
    return LensResult(
        lens_id=LENS_ID,
        version=VERSION,
        status=status,
        score=None if score is None else round(score, 2),
        components=components,
        exclusions=tuple(exclusions),
        methodology_id="investor_lens_factor_quality",
        inputs_used=("factor_exposures", "fundamentals"),
    )
