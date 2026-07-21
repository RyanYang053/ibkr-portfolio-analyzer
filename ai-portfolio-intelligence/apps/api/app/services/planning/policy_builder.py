"""Build investment policy from plan inputs and risk preference."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.schemas.financial_plan import FinancialGoal, InvestmentPolicy

RISK_PRESETS: dict[str, dict[str, float]] = {
    "conservative": {
        "max_single_position_pct": 5.0,
        "max_sector_pct": 25.0,
        "max_speculative_pct": 2.0,
        "min_cash_pct": 5.0,
        "target_equity_pct": 40.0,
        "target_fixed_income_pct": 50.0,
        "rebalance_band_pct": 3.0,
    },
    "moderate": {
        "max_single_position_pct": 10.0,
        "max_sector_pct": 35.0,
        "max_speculative_pct": 5.0,
        "min_cash_pct": 2.0,
        "target_equity_pct": 70.0,
        "target_fixed_income_pct": 25.0,
        "rebalance_band_pct": 5.0,
    },
    "aggressive": {
        "max_single_position_pct": 15.0,
        "max_sector_pct": 45.0,
        "max_speculative_pct": 10.0,
        "min_cash_pct": 1.0,
        "target_equity_pct": 90.0,
        "target_fixed_income_pct": 5.0,
        "rebalance_band_pct": 7.0,
    },
}


def build_policy(
    *,
    risk_tolerance: str = "moderate",
    goals: list[FinancialGoal] | None = None,
    existing: InvestmentPolicy | None = None,
    prohibited_symbols: list[str] | None = None,
) -> InvestmentPolicy:
    preset = RISK_PRESETS.get(risk_tolerance, RISK_PRESETS["moderate"])
    horizon_years = 10
    if goals:
        # Prefer shorter-horizon goals for tighter risk bands
        dated = [g for g in goals if g.target_date is not None]
        if dated:
            from datetime import date

            today = date.today()
            horizons = []
            for g in dated:
                assert g.target_date is not None
                years = max((g.target_date - today).days / 365.25, 0.5)
                horizons.append(years)
            horizon_years = int(min(horizons))

    policy_id = existing.policy_id if existing else f"pol_{uuid4().hex[:12]}"
    version = existing.version if existing else "1.0.0"
    constraints = dict(existing.constraints) if existing else {}
    if horizon_years < 5:
        constraints["short_horizon"] = True
        preset = {**preset, "max_speculative_pct": min(preset["max_speculative_pct"], 2.0)}

    return InvestmentPolicy(
        policy_id=policy_id,
        version=version,
        risk_tolerance=risk_tolerance if risk_tolerance in RISK_PRESETS else "moderate",
        max_single_position_pct=preset["max_single_position_pct"],
        max_sector_pct=preset["max_sector_pct"],
        max_speculative_pct=preset["max_speculative_pct"],
        min_cash_pct=preset["min_cash_pct"],
        target_equity_pct=preset["target_equity_pct"],
        target_fixed_income_pct=preset["target_fixed_income_pct"],
        rebalance_band_pct=preset["rebalance_band_pct"],
        tax_loss_harvesting=existing.tax_loss_harvesting if existing else False,
        prohibited_symbols=list(prohibited_symbols or (existing.prohibited_symbols if existing else [])),
        preferred_asset_classes=list(existing.preferred_asset_classes) if existing else ["ETF", "STK"],
        constraints=constraints,
        updated_at=datetime.now(timezone.utc),
    )
