import math
from collections import defaultdict
from typing import Any
from app.schemas.domain import (
    AdvancedRiskMetrics,
    Position,
    StressScenario
)
from app.services.portfolio.pnl_tracker import PortfolioPnLSnapshot

# Scenario shock multipliers. These are assumptions, not measured security betas.
BETA_VALUES = {
    "SPY": 1.0,
    "QQQ": 1.18,
    "MSFT": 1.24,
    "META": 1.35,
    "GOOGL": 1.12,
    "SOXX": 1.55,
    "SOFI": 1.65,
    "CRM": 1.21,
    "CELH": 1.52,
    "NKE": 0.98,
    "IONQ": 2.25,
    "LAES": 2.45,
    "INFQ": 2.05,
}

def calculate_advanced_risk_metrics(
    positions: list[Position],
    summary: Any,
    history: list[PortfolioPnLSnapshot]
) -> AdvancedRiskMetrics:
    """Calculate advanced risk statistics and run stress tests on current portfolio holdings."""
    total_value = max(summary.net_liquidation, 1.0)
    
    # Account-value history is not cash-flow adjusted, so drawdown is withheld
    # until enough observations exist and remains explicitly qualified.
    max_dd = None
    if len(history) >= 2:
        measured_dd = 0.0
        peak = history[0].net_liquidation
        for entry in history:
            if entry.net_liquidation > peak:
                peak = entry.net_liquidation
            if peak > 0:
                dd = (peak - entry.net_liquidation) / peak * 100.0
                if dd > measured_dd:
                    measured_dd = dd
        max_dd = round(measured_dd, 2)

    # 2. Daily Volatility (Standard Deviation of returns)
    daily_returns = []
    if len(history) >= 2:
        for i in range(1, len(history)):
            prev = history[i-1].net_liquidation
            curr = history[i].net_liquidation
            if prev > 0:
                daily_returns.append((curr - prev) / prev * 100.0)
                
    enough_history = len(daily_returns) >= 20
    daily_vol = None
    annualized_vol = None
    if enough_history:
        mean_ret = sum(daily_returns) / len(daily_returns)
        var_ret = sum((r - mean_ret) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
        daily_vol = math.sqrt(var_ret)
        annualized_vol = daily_vol * math.sqrt(252)

    value_at_risk_95 = total_value * (1.65 * daily_vol / 100.0) if daily_vol is not None else None
    conditional_var_95 = total_value * (2.06 * daily_vol / 100.0) if daily_vol is not None else None

    # Benchmark and per-security return series are not available in this module.
    portfolio_beta_spy = None
    portfolio_beta_qqq = None
    correlation_matrix: dict[str, dict[str, float]] = {}

    # 6. Factor Exposure (Value vs Growth, Size, Momentum)
    # Estimate exposures based on holding types
    factor_exposures = {
        "Growth": 0.0,
        "Value": 0.0,
        "Momentum": 0.0,
        "Low Volatility": 0.0
    }
    
    for pos in positions:
        w = pos.portfolio_weight
        if pos.is_speculative:
            factor_exposures["Growth"] += w * 0.8
            factor_exposures["Momentum"] += w * 0.2
        elif pos.is_etf:
            if pos.symbol == "QQQ":
                factor_exposures["Growth"] += w * 0.7
                factor_exposures["Momentum"] += w * 0.3
            else:
                factor_exposures["Value"] += w * 0.5
                factor_exposures["Low Volatility"] += w * 0.5
        else:
            if pos.symbol in ("MSFT", "META", "GOOGL", "CRM"):
                factor_exposures["Growth"] += w * 0.6
                factor_exposures["Momentum"] += w * 0.4
            else:
                factor_exposures["Value"] += w * 0.6
                factor_exposures["Low Volatility"] += w * 0.4

    # Normalize exposures to sum to 100 (excluding cash)
    factor_sum = sum(factor_exposures.values()) or 1.0
    factor_exposures_pct = {k: round(v / factor_sum * 100, 2) for k, v in factor_exposures.items()}

    # 7. Stress Test Scenarios
    # Define beta-adjusted drops or shocks for each scenario
    scenarios_definition = [
        {
            "name": "Illustrative pandemic-style equity shock",
            "desc": "Assumption-based scenario: broad equities fall 30%; this is not a historical replay.",
            "mkt_shock": -30.0,
            "spec_shock": -45.0,
            "opt_shock": -90.0,
        },
        {
            "name": "Illustrative inflation and rate shock",
            "desc": "Assumption-based scenario: broad equities fall 20% and speculative assets fall 55%.",
            "mkt_shock": -20.0,
            "spec_shock": -55.0,
            "opt_shock": -75.0,
        },
        {
            "name": "Illustrative technology valuation shock",
            "desc": "Assumption-based scenario: technology and speculative assets experience severe valuation compression.",
            "mkt_shock": -50.0,
            "spec_shock": -85.0,
            "opt_shock": -95.0,
        },
        {
            "name": "Illustrative systemic credit shock",
            "desc": "Assumption-based scenario: broad equities fall 45% and speculative assets fall 65%.",
            "mkt_shock": -45.0,
            "spec_shock": -65.0,
            "opt_shock": -85.0,
        }
    ]

    stress_tests: list[StressScenario] = []
    
    for sc in scenarios_definition:
        shock_val = 0.0
        for pos in positions:
            # Calculate shock on each position based on its type
            if pos.asset_class == "OPT":
                asset_drop = sc["opt_shock"]
            elif pos.is_speculative:
                asset_drop = sc["spec_shock"]
            elif pos.symbol == "QQQ" or pos.sector == "Technology":
                # Tech is hit harder in 2022 and 2000 scenarios
                if "technology valuation" in sc["name"]:
                    asset_drop = -75.0
                elif "inflation and rate" in sc["name"]:
                    asset_drop = -33.0
                else:
                    asset_drop = sc["mkt_shock"] * BETA_VALUES.get(pos.symbol, 1.1)
            else:
                asset_drop = sc["mkt_shock"] * BETA_VALUES.get(pos.symbol, 1.0)
                
            # Cap drop at -100% (cannot lose more than position value)
            asset_drop = max(-100.0, asset_drop)
            shock_val += pos.market_value * (asset_drop / 100.0)
            
        portfolio_change_pct = (shock_val / total_value) * 100.0
        
        # Risk levels mapping
        risk_lvl = "Low"
        if abs(portfolio_change_pct) > 25.0:
            risk_lvl = "High"
        elif abs(portfolio_change_pct) > 12.0:
            risk_lvl = "Medium"
            
        stress_tests.append(
            StressScenario(
                name=sc["name"],
                description=sc["desc"],
                portfolio_change_pct=round(portfolio_change_pct, 2),
                estimated_loss=round(abs(shock_val), 2),
                risk_level=risk_lvl
            )
        )

    return AdvancedRiskMetrics(
        max_drawdown=max_dd,
        volatility=round(annualized_vol, 2) if annualized_vol is not None else None,
        portfolio_beta_spy=portfolio_beta_spy,
        portfolio_beta_qqq=portfolio_beta_qqq,
        value_at_risk_95=round(value_at_risk_95, 2) if value_at_risk_95 is not None else None,
        conditional_var_95=round(conditional_var_95, 2) if conditional_var_95 is not None else None,
        correlation_matrix=dict(correlation_matrix),
        factor_exposures=factor_exposures_pct,
        stress_tests=stress_tests,
        data_quality={
            "historical_metrics": "sufficient" if enough_history else "insufficient",
            "benchmark_returns": "missing",
            "security_return_series": "missing",
        },
        methodology={
            "drawdown": "Account-value drawdown; not adjusted for deposits or withdrawals.",
            "volatility_var": "Sample volatility and parametric 95% VaR require at least 20 daily returns.",
            "beta_correlation": "Unavailable without aligned benchmark and security return series.",
            "factor_exposures": "Heuristic classification, not a fitted factor model.",
            "stress_tests": "Illustrative assumption-based scenarios, not forecasts.",
        },
    )
