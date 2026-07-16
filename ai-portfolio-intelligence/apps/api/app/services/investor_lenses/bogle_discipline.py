from __future__ import annotations

from app.services.investor_lenses.base import LensComponent, LensInputs, LensResult, _clamp, _mean_available, _num

LENS_ID = "bogle_discipline"
VERSION = "0.1.0"


def evaluate(inputs: LensInputs) -> LensResult:
    pos = inputs.position
    liq = inputs.liquidity
    exclusions: list[str] = []
    weight = _num(pos, "portfolio_weight", "weight")
    turnover_proxy = _num(liq, "participation_rate", "adv_participation")
    is_etf = bool(pos.get("is_etf") or str(pos.get("asset_class") or "").upper() in {"ETF", "STK"} and pos.get("stock_type") == "etf")

    concentration_score = None if weight is None else _clamp(100.0 - max(weight - 5.0, 0.0) * 8.0)
    turnover_score = None if turnover_proxy is None else _clamp(100.0 - abs(turnover_proxy) * 200.0)
    simplicity_score = 80.0 if is_etf else 55.0
    if weight is None:
        exclusions.append("portfolio_weight_missing")
    if turnover_proxy is None:
        exclusions.append("liquidity_turnover_proxy_missing")

    components = (
        LensComponent("concentration_discipline", concentration_score, ("position.portfolio_weight",)),
        LensComponent("turnover_discipline", turnover_score, ("liquidity.participation_rate",)),
        LensComponent("simplicity_bias", simplicity_score, ("position.asset_class",)),
    )
    score = _mean_available([concentration_score, turnover_score, simplicity_score])
    status = "withheld" if score is None else ("provisional" if exclusions else "available")
    return LensResult(
        lens_id=LENS_ID,
        version=VERSION,
        status=status,
        score=None if score is None else round(score, 2),
        components=components,
        exclusions=tuple(exclusions),
        methodology_id="investor_lens_bogle_discipline",
        inputs_used=("position", "liquidity"),
    )
