import json
import os
from collections import defaultdict
from typing import Any
from app.schemas.domain import InvestmentPolicyStatement, Position, AccountSummary

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
    "rebalancing_drift_threshold": 5.0
}


def get_portfolio_policy(account_id: str = "default") -> InvestmentPolicyStatement:
    """Load the IPS policy, seeding defaults if not present."""
    os.makedirs(DATA_DIR, exist_ok=True)
    policy_path = POLICY_FILE
    if account_id and account_id != "default":
        policy_path = os.path.join(DATA_DIR, f"portfolio_policy_{account_id}.json")
        if not os.path.exists(policy_path) and os.path.exists(POLICY_FILE):
            policy_path = POLICY_FILE

    if not os.path.exists(policy_path):
        with open(policy_path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_POLICY, f, indent=2)
        return InvestmentPolicyStatement(**DEFAULT_POLICY)

    try:
        with open(policy_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return InvestmentPolicyStatement(**data)
    except Exception:
        return InvestmentPolicyStatement(**DEFAULT_POLICY)


def save_portfolio_policy(policy: InvestmentPolicyStatement, account_id: str = "default") -> None:
    """Save the IPS policy."""
    os.makedirs(DATA_DIR, exist_ok=True)
    policy_path = os.path.join(DATA_DIR, f"portfolio_policy_{account_id}.json") if account_id and account_id != "default" else POLICY_FILE
    with open(policy_path, "w", encoding="utf-8") as f:
        json.dump(policy.model_dump(), f, indent=2)


def analyze_policy_drift(positions: list[Position], cash: float, total_val: float, policy: InvestmentPolicyStatement) -> dict[str, Any]:
    """Calculate asset and sector allocation drift vs policy targets."""
    total_val = max(total_val, 1.0)
    
    # Group by asset classes: Equity (STK/ETF), Cash, Bond (BND/Fixed Income)
    equity_val = 0.0
    bond_val = 0.0
    options_val = 0.0
    speculative_val = 0.0
    
    sector_mv = defaultdict(float)
    single_stock_mv = defaultdict(float)
    
    for pos in positions:
        mv = pos.market_value
        if pos.asset_class == "OPT":
            options_val += mv
        elif "BND" in pos.asset_class or "BOND" in pos.asset_class or pos.asset_class == "FI":
            bond_val += mv
        else:
            # Default to equity
            equity_val += mv
            
        if pos.is_speculative:
            speculative_val += mv
            
        if not pos.is_etf and pos.asset_class != "OPT":
            single_stock_mv[pos.symbol] += mv
            
        sector_mv[pos.sector] += mv

    current_equity_pct = (equity_val / total_val) * 100
    current_cash_pct = (cash / total_val) * 100
    current_bond_pct = (bond_val / total_val) * 100
    current_options_pct = (options_val / total_val) * 100
    current_speculative_pct = (speculative_val / total_val) * 100

    drifts = {
        "equity": {
            "current": round(current_equity_pct, 2),
            "target": policy.target_equity_percent,
            "drift": round(current_equity_pct - policy.target_equity_percent, 2)
        },
        "cash": {
            "current": round(current_cash_pct, 2),
            "target": policy.target_cash_percent,
            "drift": round(current_cash_pct - policy.target_cash_percent, 2)
        },
        "bond": {
            "current": round(current_bond_pct, 2),
            "target": policy.target_bond_percent,
            "drift": round(current_bond_pct - policy.target_bond_percent, 2)
        }
    }

    # Find policy violations/drift warnings
    warnings = []
    rebalance_triggered = False

    # Check drift thresholds
    for asset, details in drifts.items():
        if abs(details["drift"]) > policy.rebalancing_drift_threshold:
            rebalance_triggered = True
            warnings.append(
                f"Asset class {asset.capitalize()} has drifted by {details['drift']:.2f}% (exceeds threshold of {policy.rebalancing_drift_threshold}%)."
            )

    # Check cash floor
    if cash < policy.minimum_cash:
        warnings.append(
            f"Cash balance ({cash:.2f}) is below minimum floor limit ({policy.minimum_cash:.2f})."
        )

    # Check single stock concentration limit
    for symbol, mv in single_stock_mv.items():
        weight = (mv / total_val) * 100
        if weight > policy.max_single_stock_weight:
            warnings.append(
                f"Single stock concentration in {symbol} is {weight:.2f}% (exceeds policy limit of {policy.max_single_stock_weight}%)."
            )

    # Check speculative limit
    if current_speculative_pct > policy.max_speculative_weight:
        warnings.append(
            f"Total speculative asset concentration is {current_speculative_pct:.2f}% (exceeds policy limit of {policy.max_speculative_weight}%)."
        )

    # Check sector limits
    for sector, mv in sector_mv.items():
        weight = (mv / total_val) * 100
        if sector and sector != "Unknown" and weight > policy.max_sector_weight:
            warnings.append(
                f"Sector concentration in {sector} is {weight:.2f}% (exceeds policy limit of {policy.max_sector_weight}%)."
            )

    # Check options limits
    if current_options_pct > policy.max_options_exposure:
        warnings.append(
            f"Options exposure is {current_options_pct:.2f}% (exceeds policy limit of {policy.max_options_exposure}%)."
        )

    return {
        "drifts": drifts,
        "speculative_percent": round(current_speculative_pct, 2),
        "options_percent": round(current_options_pct, 2),
        "rebalance_triggered": rebalance_triggered,
        "warnings": warnings
    }
