from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from typing import Any, Callable

from app.schemas.domain import InvestmentPolicyStatement, Position

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
POLICY_FILE = os.path.join(DATA_DIR, "portfolio_policy.json")

DEFAULT_POLICY = {
    "target_equity_percent": 85.0,
    "target_cash_percent": 15.0,
    "target_bond_percent": 0.0,
    "max_single_stock_weight": 12.0,
    "max_speculative_weight": 5.0,
    "max_sector_weight": 35.0,
    "max_options_exposure": 3.0,
    "minimum_cash": 10000.0,
    "benchmark": "SPY",
    "rebalancing_drift_threshold": 5.0,
}


def get_portfolio_policy(account_id: str = "default") -> InvestmentPolicyStatement:
    """Load the IPS policy, seeding defaults if not present."""
    from app.db.legacy_bridge import read_json_with_legacy, write_json_state

    policy_path = POLICY_FILE
    if account_id and account_id != "default":
        policy_path = os.path.join(DATA_DIR, f"portfolio_policy_{account_id}.json")
        if not os.path.exists(policy_path) and os.path.exists(POLICY_FILE):
            policy_path = POLICY_FILE

    record_key = account_id or "default"
    data = read_json_with_legacy("portfolio_policy", record_key, policy_path if os.path.exists(policy_path) else None, default=None)
    if data is None:
        write_json_state("portfolio_policy", record_key, DEFAULT_POLICY)
        return InvestmentPolicyStatement(**DEFAULT_POLICY)

    try:
        return InvestmentPolicyStatement(**data)
    except Exception:
        return InvestmentPolicyStatement(**DEFAULT_POLICY)


def save_portfolio_policy(policy: InvestmentPolicyStatement, account_id: str = "default") -> None:
    """Save the IPS policy."""
    from app.db.legacy_bridge import write_json_state

    record_key = account_id or "default"
    write_json_state("portfolio_policy", record_key, policy.model_dump())
    os.makedirs(DATA_DIR, exist_ok=True)
    policy_path = (
        os.path.join(DATA_DIR, f"portfolio_policy_{account_id}.json")
        if account_id and account_id != "default"
        else POLICY_FILE
    )
    with open(policy_path, "w", encoding="utf-8") as handle:
        json.dump(policy.model_dump(), handle, indent=2)


def analyze_policy_drift(
    positions: list[Position],
    cash: float,
    total_val: float,
    policy: InvestmentPolicyStatement,
    *,
    base_currency: str | None = None,
    fx_resolver: Callable[[str, str], float] | None = None,
) -> dict[str, Any]:
    """Calculate gross exposure and allocation drift in one reporting currency.

    Individual-account positions may be denominated in several currencies while
    net liquidation is reported in the account base currency. Every position is
    therefore converted before policy percentages are calculated. Gross absolute
    exposure is used for concentration and derivative limits so shorts cannot
    cancel longs.
    """
    if not math.isfinite(float(total_val)) or total_val <= 0:
        raise ValueError("Total portfolio value must be finite and positive")

    if base_currency is None:
        base_currency = ""
    base_currency = base_currency.upper().strip()

    def converted_value(position: Position) -> float:
        value = float(position.market_value)
        if not math.isfinite(value):
            raise ValueError(f"Non-finite market value for {position.symbol}")
        if not base_currency or position.currency.upper().strip() == base_currency:
            return value
        if fx_resolver is None:
            raise ValueError(
                f"FX resolver is required to convert {position.symbol} from {position.currency} to {base_currency}"
            )
        rate = float(fx_resolver(position.currency, base_currency))
        if not math.isfinite(rate) or rate <= 0:
            raise ValueError(f"Invalid FX rate for {position.currency}/{base_currency}: {rate}")
        return value * rate

    equity_val = 0.0
    bond_val = 0.0
    options_val = 0.0
    speculative_val = 0.0
    sector_mv: dict[str, float] = defaultdict(float)
    single_stock_mv: dict[str, float] = defaultdict(float)

    for position in positions:
        gross_value = abs(converted_value(position))
        if position.asset_class in {"OPT", "FOP"}:
            options_val += gross_value
        elif "BND" in position.asset_class or "BOND" in position.asset_class or position.asset_class == "FI":
            bond_val += gross_value
        else:
            equity_val += gross_value

        if position.is_speculative:
            speculative_val += gross_value
        if not position.is_etf and position.asset_class not in {"OPT", "FOP"}:
            single_stock_mv[position.symbol] += gross_value
        sector_mv[position.sector or "Unknown"] += gross_value

    current_equity_pct = equity_val / total_val * 100.0
    current_cash_pct = float(cash) / total_val * 100.0
    current_bond_pct = bond_val / total_val * 100.0
    current_options_pct = options_val / total_val * 100.0
    current_speculative_pct = speculative_val / total_val * 100.0

    drifts = {
        "equity": {
            "current": round(current_equity_pct, 2),
            "target": policy.target_equity_percent,
            "drift": round(current_equity_pct - policy.target_equity_percent, 2),
        },
        "cash": {
            "current": round(current_cash_pct, 2),
            "target": policy.target_cash_percent,
            "drift": round(current_cash_pct - policy.target_cash_percent, 2),
        },
        "bond": {
            "current": round(current_bond_pct, 2),
            "target": policy.target_bond_percent,
            "drift": round(current_bond_pct - policy.target_bond_percent, 2),
        },
    }

    warnings: list[str] = []
    rebalance_triggered = False
    for asset, details in drifts.items():
        if abs(float(details["drift"])) > policy.rebalancing_drift_threshold:
            rebalance_triggered = True
            warnings.append(
                f"Asset class {asset.capitalize()} has drifted by {details['drift']:.2f}% "
                f"(exceeds threshold of {policy.rebalancing_drift_threshold}%)."
            )

    if cash < policy.minimum_cash:
        warnings.append(f"Cash balance ({cash:.2f}) is below minimum floor limit ({policy.minimum_cash:.2f}).")

    for symbol, market_value in single_stock_mv.items():
        weight = market_value / total_val * 100.0
        if weight > policy.max_single_stock_weight:
            warnings.append(
                f"Single stock concentration in {symbol} is {weight:.2f}% "
                f"(exceeds policy limit of {policy.max_single_stock_weight}%)."
            )

    if current_speculative_pct > policy.max_speculative_weight:
        warnings.append(
            f"Total speculative asset concentration is {current_speculative_pct:.2f}% "
            f"(exceeds policy limit of {policy.max_speculative_weight}%)."
        )

    for sector, market_value in sector_mv.items():
        weight = market_value / total_val * 100.0
        if sector != "Unknown" and weight > policy.max_sector_weight:
            warnings.append(
                f"Sector concentration in {sector} is {weight:.2f}% "
                f"(exceeds policy limit of {policy.max_sector_weight}%)."
            )

    if current_options_pct > policy.max_options_exposure:
        warnings.append(
            f"Options exposure is {current_options_pct:.2f}% "
            f"(exceeds policy limit of {policy.max_options_exposure}%)."
        )

    return {
        "drifts": drifts,
        "speculative_percent": round(current_speculative_pct, 2),
        "options_percent": round(current_options_pct, 2),
        "gross_invested_exposure_percent": round(
            (equity_val + bond_val + options_val) / total_val * 100.0,
            2,
        ),
        "reporting_currency": base_currency or "position_native_assumed",
        "rebalance_triggered": rebalance_triggered,
        "warnings": warnings,
    }
