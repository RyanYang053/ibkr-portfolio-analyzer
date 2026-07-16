from __future__ import annotations

from app.services.investor_lenses.base import LensComponent, LensInputs, LensResult, _clamp, _mean_available, _num

LENS_ID = "greenblatt"
VERSION = "0.1.0"


def evaluate(inputs: LensInputs) -> LensResult:
    f = inputs.fundamentals
    exclusions: list[str] = []
    roe = _num(f, "return_on_equity", "return_on_tangible_equity")
    earnings_yield = None
    pe = _num(f, "pe_forward")
    if pe is not None and pe > 0:
        earnings_yield = 1.0 / pe
    fcf_yield = _num(f, "fcf_yield")

    roe_score = None if roe is None else _clamp((roe / 0.25) * 100.0)
    ey_score = None if earnings_yield is None else _clamp((earnings_yield / 0.08) * 100.0)
    fcf_score = None if fcf_yield is None else _clamp((fcf_yield / 0.08) * 100.0)
    if roe is None:
        exclusions.append("roe_missing")
    if earnings_yield is None:
        exclusions.append("earnings_yield_missing")
    if fcf_yield is None:
        exclusions.append("fcf_yield_missing")

    components = (
        LensComponent("return_on_capital_proxy", roe_score, ("fundamentals.return_on_equity",)),
        LensComponent("earnings_yield", ey_score, ("fundamentals.pe_forward",)),
        LensComponent("fcf_yield", fcf_score, ("fundamentals.fcf_yield",)),
    )
    score = _mean_available([roe_score, ey_score, fcf_score])
    status = "withheld" if score is None else ("provisional" if exclusions else "available")
    return LensResult(
        lens_id=LENS_ID,
        version=VERSION,
        status=status,
        score=None if score is None else round(score, 2),
        components=components,
        exclusions=tuple(exclusions),
        methodology_id="investor_lens_greenblatt",
        inputs_used=("fundamentals",),
    )
