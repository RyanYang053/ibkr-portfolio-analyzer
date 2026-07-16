from __future__ import annotations

from app.services.investor_lenses.base import (
    LensComponent,
    LensInputs,
    LensResult,
    _clamp,
    _mean_available,
    _num,
)

LENS_ID = "buffett_quality"
VERSION = "0.1.0"


def evaluate(inputs: LensInputs) -> LensResult:
    f = inputs.fundamentals
    roe = _num(f, "return_on_equity")
    fcf_yield = _num(f, "fcf_yield")
    operating_margin = _num(f, "operating_margin")
    debt = _num(f, "total_debt")
    equity = _num(f, "average_common_equity", "tangible_common_equity")
    exclusions: list[str] = []
    components: list[LensComponent] = []

    roe_score = None if roe is None else _clamp((roe / 0.20) * 100.0)
    components.append(LensComponent("roe", roe_score, ("fundamentals.return_on_equity",)))
    if roe is None:
        exclusions.append("roe_missing")

    fcf_score = None if fcf_yield is None else _clamp((fcf_yield / 0.06) * 100.0)
    components.append(LensComponent("fcf_yield", fcf_score, ("fundamentals.fcf_yield",)))
    if fcf_yield is None:
        exclusions.append("fcf_yield_missing")

    margin_score = None if operating_margin is None else _clamp((operating_margin / 0.25) * 100.0)
    components.append(LensComponent("operating_margin", margin_score, ("fundamentals.operating_margin",)))
    if operating_margin is None:
        exclusions.append("operating_margin_missing")

    leverage_score = None
    if debt is not None and equity is not None and equity > 0:
        leverage_score = _clamp(100.0 - (debt / equity) * 40.0)
    else:
        exclusions.append("leverage_inputs_missing")
    components.append(LensComponent("conservative_leverage", leverage_score, ("fundamentals.total_debt",)))

    score = _mean_available([roe_score, fcf_score, margin_score, leverage_score])
    status = "withheld" if score is None else ("provisional" if exclusions else "available")
    return LensResult(
        lens_id=LENS_ID,
        version=VERSION,
        status=status,
        score=None if score is None else round(score, 2),
        components=tuple(components),
        exclusions=tuple(exclusions),
        evidence_refs=("fundamentals",),
        methodology_id="investor_lens_buffett_quality",
        inputs_used=("fundamentals",),
    )
