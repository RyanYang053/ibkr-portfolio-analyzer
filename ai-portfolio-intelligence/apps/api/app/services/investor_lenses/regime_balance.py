from __future__ import annotations

from app.services.investor_lenses.base import LensComponent, LensInputs, LensResult, _clamp, _mean_available, _num

LENS_ID = "regime_balance"
VERSION = "0.1.0"


def evaluate(inputs: LensInputs) -> LensResult:
    f = inputs.factor_exposures
    exclusions: list[str] = []
    market = _num(f, "market", "mkt")
    value = _num(f, "value")
    momentum = _num(f, "momentum", "mom")
    quality = _num(f, "quality")
    if not f:
        exclusions.append("factor_exposures_missing")

    # Prefer balanced (near-zero) active exposures for regime resilience.
    def _balance(x: float | None) -> float | None:
        if x is None:
            return None
        return _clamp(100.0 - abs(x) * 100.0)

    components = (
        LensComponent("market_balance", _balance(market), ("factors.market",)),
        LensComponent("value_balance", _balance(value), ("factors.value",)),
        LensComponent("momentum_balance", _balance(momentum), ("factors.momentum",)),
        LensComponent("quality_balance", _balance(quality), ("factors.quality",)),
    )
    score = _mean_available([c.value for c in components])
    status = "withheld" if score is None else ("provisional" if exclusions else "available")
    return LensResult(
        lens_id=LENS_ID,
        version=VERSION,
        status=status,
        score=None if score is None else round(score, 2),
        components=components,
        exclusions=tuple(exclusions),
        methodology_id="investor_lens_regime_balance",
        inputs_used=("factor_exposures",),
    )
