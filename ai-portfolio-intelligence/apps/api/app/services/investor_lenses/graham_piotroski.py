from __future__ import annotations

from app.services.investor_lenses.base import LensComponent, LensInputs, LensResult, _clamp, _num

LENS_ID = "graham_piotroski"
VERSION = "0.1.0"


def evaluate(inputs: LensInputs) -> LensResult:
    f = inputs.fundamentals
    exclusions: list[str] = []
    flags: list[LensComponent] = []

    def _flag(name: str, ok: bool | None, refs: tuple[str, ...]) -> None:
        if ok is None:
            exclusions.append(f"{name}_missing")
            flags.append(LensComponent(name, None, refs))
        else:
            flags.append(LensComponent(name, 1.0 if ok else 0.0, refs))

    ni = _num(f, "net_income_common")
    ocf = _num(f, "operating_cash_flow")
    roe = _num(f, "return_on_equity")
    debt = _num(f, "total_debt")
    cash = _num(f, "cash")
    pe = _num(f, "pe_forward")
    ptb = _num(f, "price_to_tangible_book")

    _flag("positive_net_income", None if ni is None else ni > 0, ("fundamentals.net_income_common",))
    _flag("positive_operating_cash_flow", None if ocf is None else ocf > 0, ("fundamentals.operating_cash_flow",))
    _flag(
        "cash_exceeds_net_income",
        None if (ocf is None or ni is None) else ocf > ni,
        ("fundamentals.operating_cash_flow",),
    )
    _flag("roe_positive", None if roe is None else roe > 0, ("fundamentals.return_on_equity",))
    _flag("low_leverage", None if debt is None else debt >= 0, ("fundamentals.total_debt",))
    _flag("cash_buffer", None if cash is None else cash > 0, ("fundamentals.cash",))
    _flag("value_pe", None if pe is None else pe < 20, ("fundamentals.pe_forward",))
    _flag("value_ptb", None if ptb is None else ptb < 1.5, ("fundamentals.price_to_tangible_book",))

    present = [c.value for c in flags if c.value is not None]
    if not present:
        return LensResult(
            lens_id=LENS_ID,
            version=VERSION,
            status="withheld",
            score=None,
            components=tuple(flags),
            exclusions=tuple(exclusions),
            methodology_id="investor_lens_graham_piotroski",
            inputs_used=("fundamentals",),
        )
    score = _clamp(100.0 * sum(present) / len(present))
    status = "provisional" if exclusions else "available"
    return LensResult(
        lens_id=LENS_ID,
        version=VERSION,
        status=status,
        score=round(score, 2),
        components=tuple(flags),
        exclusions=tuple(exclusions),
        evidence_refs=("fundamentals",),
        methodology_id="investor_lens_graham_piotroski",
        inputs_used=("fundamentals",),
    )
