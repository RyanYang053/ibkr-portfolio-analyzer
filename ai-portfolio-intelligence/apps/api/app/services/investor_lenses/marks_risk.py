from __future__ import annotations

from app.services.investor_lenses.base import LensComponent, LensInputs, LensResult, _clamp, _mean_available, _num

LENS_ID = "marks_risk"
VERSION = "0.1.0"


def evaluate(inputs: LensInputs) -> LensResult:
    r = inputs.risk_metrics
    exclusions: list[str] = []
    vol = _num(r, "volatility", "ewma_volatility")
    max_dd = _num(r, "max_drawdown")
    cvar = _num(r, "conditional_var_95", "value_at_risk_95")

    vol_score = None if vol is None else _clamp(100.0 - abs(vol) * 2.0)
    dd_score = None if max_dd is None else _clamp(100.0 - abs(max_dd) * 2.0)
    cvar_score = None if cvar is None else _clamp(100.0 - abs(cvar) * 2.0)
    if vol is None:
        exclusions.append("volatility_missing")
    if max_dd is None:
        exclusions.append("max_drawdown_missing")
    if cvar is None:
        exclusions.append("tail_risk_missing")

    components = (
        LensComponent("volatility", vol_score, ("risk.volatility",)),
        LensComponent("max_drawdown", dd_score, ("risk.max_drawdown",)),
        LensComponent("tail_risk", cvar_score, ("risk.conditional_var_95",)),
    )
    score = _mean_available([vol_score, dd_score, cvar_score])
    status = "withheld" if score is None else ("provisional" if exclusions else "available")
    return LensResult(
        lens_id=LENS_ID,
        version=VERSION,
        status=status,
        score=None if score is None else round(score, 2),
        components=components,
        exclusions=tuple(exclusions),
        methodology_id="investor_lens_marks_risk",
        inputs_used=("risk_metrics",),
    )
