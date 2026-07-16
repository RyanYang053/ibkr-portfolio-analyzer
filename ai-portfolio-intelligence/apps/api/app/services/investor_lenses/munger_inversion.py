from __future__ import annotations

from app.services.investor_lenses.base import LensComponent, LensInputs, LensResult, _clamp, _mean_available, _num

LENS_ID = "munger_inversion"
VERSION = "0.1.0"


def evaluate(inputs: LensInputs) -> LensResult:
    """Score by absence of failure modes (inversion), not guru-average optimism."""
    f = inputs.fundamentals
    r = inputs.risk_metrics
    tax = inputs.tax_flags
    exclusions: list[str] = []

    debt = _num(f, "total_debt")
    cash = _num(f, "cash")
    ni = _num(f, "net_income_common")
    max_dd = _num(r, "max_drawdown")
    provisional_tax = str(tax.get("methodology_status") or "").startswith("provisional")

    leverage_ok = None
    if debt is not None and cash is not None:
        leverage_ok = debt <= cash * 5
    elif debt is not None:
        leverage_ok = debt >= 0
    earnings_ok = None if ni is None else ni > 0
    drawdown_ok = None if max_dd is None else abs(max_dd) < 40.0

    components = [
        LensComponent("avoid_excessive_leverage", None if leverage_ok is None else (100.0 if leverage_ok else 20.0), ("fundamentals.total_debt",)),
        LensComponent("avoid_losses", None if earnings_ok is None else (100.0 if earnings_ok else 10.0), ("fundamentals.net_income_common",)),
        LensComponent("avoid_deep_drawdown", None if drawdown_ok is None else (100.0 if drawdown_ok else 25.0), ("risk.max_drawdown",)),
        LensComponent(
            "tax_uncertainty_penalty",
            40.0 if provisional_tax else 80.0,
            ("tax.methodology_status",),
            note="provisional tax labeling reduces confidence",
        ),
    ]
    for name, ok in (
        ("leverage", leverage_ok),
        ("earnings", earnings_ok),
        ("drawdown", drawdown_ok),
    ):
        if ok is None:
            exclusions.append(f"{name}_missing")

    score = _mean_available([c.value for c in components])
    status = "withheld" if score is None else ("provisional" if exclusions or provisional_tax else "available")
    return LensResult(
        lens_id=LENS_ID,
        version=VERSION,
        status=status,
        score=None if score is None else round(_clamp(score), 2),
        components=tuple(components),
        exclusions=tuple(exclusions),
        methodology_id="investor_lens_munger_inversion",
        inputs_used=("fundamentals", "risk_metrics", "tax_flags"),
    )
