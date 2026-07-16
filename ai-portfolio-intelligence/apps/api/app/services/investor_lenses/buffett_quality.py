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
LENS_DISPLAY_NAME = "Quality and Leverage Heuristic"
VERSION = "0.2.0"


def evaluate(inputs: LensInputs) -> LensResult:
    """Deterministic quality/leverage heuristic — not a complete Buffett-style appraisal."""
    f = inputs.fundamentals
    roe = _num(f, "return_on_equity")
    fcf_yield = _num(f, "fcf_yield")
    operating_margin = _num(f, "operating_margin")
    gross_margin = _num(f, "gross_margin")
    debt = _num(f, "total_debt")
    equity = _num(f, "average_common_equity", "tangible_common_equity")
    cash = _num(f, "cash")
    net_income = _num(f, "net_income_common")
    fcf = _num(f, "free_cash_flow")
    ocf = _num(f, "operating_cash_flow")
    diluted_shares = _num(f, "diluted_shares")
    prior_shares = _num(f, "diluted_shares_prior", "shares_outstanding_prior")
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

    # ROIC proxy: net income / (equity + debt - cash)
    invested_capital = None
    if equity is not None:
        invested_capital = equity + (debt or 0.0) - (cash or 0.0)
    roic_score = None
    if net_income is not None and invested_capital is not None and invested_capital > 0:
        roic = net_income / invested_capital
        roic_score = _clamp((roic / 0.12) * 100.0)
        components.append(
            LensComponent(
                "roic_proxy",
                roic_score,
                ("fundamentals.net_income_common", "fundamentals.average_common_equity"),
                note="Proxy ROIC using net income / (equity+debt-cash); not NOPAT/IC accounting ROIC.",
            )
        )
    else:
        exclusions.append("roic_inputs_missing")
        components.append(LensComponent("roic_proxy", None, ()))

    # Owner-earnings proxy: prefer FCF, else OCF with haircut.
    owner_earnings_score = None
    if fcf is not None and equity is not None and equity > 0:
        owner_yield = fcf / equity
        owner_earnings_score = _clamp((owner_yield / 0.08) * 100.0)
        components.append(
            LensComponent(
                "owner_earnings_proxy",
                owner_earnings_score,
                ("fundamentals.free_cash_flow",),
                note="Uses reported FCF as owner-earnings proxy; maintenance capex not separately modeled.",
            )
        )
    elif ocf is not None and equity is not None and equity > 0:
        owner_yield = (ocf * 0.7) / equity
        owner_earnings_score = _clamp((owner_yield / 0.08) * 100.0)
        exclusions.append("owner_earnings_used_ocf_haircut")
        components.append(
            LensComponent(
                "owner_earnings_proxy",
                owner_earnings_score,
                ("fundamentals.operating_cash_flow",),
                note="OCF*0.7 stand-in when FCF missing.",
            )
        )
    else:
        exclusions.append("owner_earnings_inputs_missing")
        components.append(LensComponent("owner_earnings_proxy", None, ()))

    # Margin durability proxy from gross vs operating gap (narrower gap = more durable).
    margin_stability_score = None
    if gross_margin is not None and operating_margin is not None and gross_margin > 0:
        gap = max(0.0, gross_margin - operating_margin)
        margin_stability_score = _clamp(100.0 - (gap / max(gross_margin, 1e-6)) * 100.0)
        components.append(
            LensComponent(
                "margin_stability_proxy",
                margin_stability_score,
                ("fundamentals.gross_margin", "fundamentals.operating_margin"),
                note="Single-period gross-to-operating gap proxy; multi-year margin history not yet wired.",
            )
        )
        exclusions.append("margin_history_not_wired")
    else:
        exclusions.append("margin_stability_inputs_missing")
        components.append(LensComponent("margin_stability_proxy", None, ()))

    # Dilution: requires prior share count.
    dilution_score = None
    if diluted_shares is not None and prior_shares is not None and prior_shares > 0:
        change = (diluted_shares / prior_shares) - 1.0
        dilution_score = _clamp(100.0 - max(0.0, change) * 500.0)
        components.append(
            LensComponent(
                "dilution",
                dilution_score,
                ("fundamentals.diluted_shares", "fundamentals.diluted_shares_prior"),
            )
        )
    else:
        exclusions.append("dilution_history_missing")
        components.append(LensComponent("dilution", None, ()))

    # Still not implemented as quantitative components — call out honestly.
    for missing in (
        "incremental_roic",
        "per_share_compounding",
        "reinvestment_runway",
        "moat_durability_score",
        "capital_allocation_score",
        "valuation_range",
    ):
        exclusions.append(f"{missing}_not_implemented")

    score = _mean_available(
        [
            roe_score,
            fcf_score,
            margin_score,
            leverage_score,
            roic_score,
            owner_earnings_score,
            margin_stability_score,
            dilution_score,
        ]
    )
    status = "withheld" if score is None else ("provisional" if exclusions else "available")
    return LensResult(
        lens_id=LENS_ID,
        display_name=LENS_DISPLAY_NAME,
        version=VERSION,
        status=status,
        score=None if score is None else round(score, 2),
        components=tuple(components),
        exclusions=tuple(exclusions),
        evidence_refs=("fundamentals",),
        methodology_id="investor_lens_buffett_quality",
        inputs_used=("fundamentals",),
    )
