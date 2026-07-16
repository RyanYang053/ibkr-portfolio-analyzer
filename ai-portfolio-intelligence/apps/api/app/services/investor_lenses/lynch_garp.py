from __future__ import annotations

from app.services.investor_lenses.base import LensComponent, LensInputs, LensResult, _clamp, _mean_available, _num

LENS_ID = "lynch_garp"
VERSION = "0.1.0"


def evaluate(inputs: LensInputs) -> LensResult:
    f = inputs.fundamentals
    exclusions: list[str] = []
    growth = _num(f, "revenue_growth_yoy")
    pe = _num(f, "pe_forward")
    peg = None
    if pe is not None and growth is not None and growth > 0:
        peg = pe / (growth * 100.0 if growth < 1 else growth)

    growth_score = None if growth is None else _clamp((growth / 0.15) * 100.0 if growth < 1 else (growth / 15.0) * 100.0)
    peg_score = None if peg is None else _clamp(100.0 - max(peg - 1.0, 0.0) * 40.0)
    if growth is None:
        exclusions.append("revenue_growth_missing")
    if peg is None:
        exclusions.append("peg_unavailable")

    components = (
        LensComponent("revenue_growth", growth_score, ("fundamentals.revenue_growth_yoy",)),
        LensComponent("peg_proxy", peg_score, ("fundamentals.pe_forward", "fundamentals.revenue_growth_yoy")),
    )
    score = _mean_available([growth_score, peg_score])
    status = "withheld" if score is None else ("provisional" if exclusions else "available")
    return LensResult(
        lens_id=LENS_ID,
        version=VERSION,
        status=status,
        score=None if score is None else round(score, 2),
        components=components,
        exclusions=tuple(exclusions),
        methodology_id="investor_lens_lynch_garp",
        inputs_used=("fundamentals",),
    )
