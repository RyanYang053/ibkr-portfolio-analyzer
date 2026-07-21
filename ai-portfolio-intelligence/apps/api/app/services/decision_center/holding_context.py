from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class HoldingContext:
    instrument_key: str
    symbol: str
    account_id: str
    data_quality: dict[str, Any] = field(default_factory=dict)
    thesis: dict[str, Any] = field(default_factory=dict)
    risk: dict[str, Any] = field(default_factory=dict)
    valuation_status: str = "withheld"
    portfolio_fit: dict[str, Any] = field(default_factory=dict)
    lens_results: list[dict[str, Any]] = field(default_factory=list)
    lens_ensemble: dict[str, Any] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    tax_flags: dict[str, Any] = field(default_factory=dict)
    liquidity: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "instrument_key": self.instrument_key,
            "symbol": self.symbol,
            "account_id": self.account_id,
            "data_quality": self.data_quality,
            "thesis": self.thesis,
            "risk": self.risk,
            "valuation_status": self.valuation_status,
            "portfolio_fit": self.portfolio_fit,
            "lens_results": self.lens_results,
            "lens_ensemble": self.lens_ensemble,
            "evidence": self.evidence,
            "tax_flags": self.tax_flags,
            "liquidity": self.liquidity,
        }


def build_holding_context(
    *,
    account_id: str,
    instrument_key: str,
    symbol: str,
    position: dict[str, Any] | None = None,
    fundamentals: dict[str, Any] | None = None,
    risk_metrics: dict[str, Any] | None = None,
    factor_exposures: dict[str, Any] | None = None,
    liquidity: dict[str, Any] | None = None,
    tax_flags: dict[str, Any] | None = None,
    thesis: dict[str, Any] | None = None,
    valuation_status: str = "withheld",
    max_single_position_pct: float | None = None,
) -> HoldingContext:
    from app.services.investor_lenses import ensemble_synthesis, evaluate_all_lenses
    from app.services.investor_lenses.base import LensInputs

    pos = dict(position or {})
    fund = dict(fundamentals or {})
    risk = dict(risk_metrics or {})
    factors = dict(factor_exposures or {})
    liq = dict(liquidity or {})
    tax = dict(tax_flags or {})
    thesis_payload = dict(thesis or {})

    # Normalize drawdown into explicit decimal units at the schema boundary.
    if "max_drawdown_decimal" not in risk and risk.get("max_drawdown") is not None:
        raw = float(risk["max_drawdown"])
        risk["max_drawdown_decimal"] = raw / 100.0 if abs(raw) > 1.0 else raw

    missing: list[str] = []
    if not fund:
        missing.append("fundamentals")
    if not risk:
        missing.append("risk_metrics")
    if not pos:
        missing.append("position")

    lens_inputs = LensInputs(
        symbol=symbol,
        fundamentals=fund,
        risk_metrics=risk,
        factor_exposures=factors,
        liquidity=liq,
        tax_flags=tax,
        position=pos,
    )
    lens_results = evaluate_all_lenses(lens_inputs)
    ensemble = ensemble_synthesis(lens_results)

    weight = float(pos.get("portfolio_weight") or pos.get("weight") or 0.0)
    max_single = float(max_single_position_pct) if max_single_position_pct is not None else 12.0
    portfolio_fit = {
        "weight_percent": weight,
        "weight": weight,
        "over_concentrated": weight > max_single,
        "max_single_position_pct": max_single,
        "status": "available" if pos else "withheld",
    }

    evidence = [
        {"type": "fundamentals", "present": bool(fund)},
        {"type": "risk", "present": bool(risk)},
        {"type": "lenses", "count": len(lens_results)},
        {"type": "thesis", "present": bool(thesis_payload.get("text") or thesis_payload.get("summary"))},
        {"type": "tax", "present": bool(tax)},
        {"type": "liquidity", "present": bool(liq)},
    ]

    return HoldingContext(
        instrument_key=instrument_key,
        symbol=symbol,
        account_id=account_id,
        data_quality={
            "status": "incomplete" if missing else "ok",
            "missing": missing,
        },
        thesis=thesis_payload,
        risk=risk,
        valuation_status=valuation_status,
        portfolio_fit=portfolio_fit,
        lens_results=[r.as_dict() for r in lens_results],
        lens_ensemble=ensemble,
        evidence=evidence,
        tax_flags=tax,
        liquidity=liq,
    )
