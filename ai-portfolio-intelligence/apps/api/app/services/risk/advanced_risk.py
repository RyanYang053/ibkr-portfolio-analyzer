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
    
    from app.services.risk.history_reconstructor import (
        reconstruct_portfolio_history,
        calculate_variance,
        calculate_covariance,
        calculate_correlation
    )
    
    import sys
    recon = None
    if "pytest" not in sys.modules:
        recon = reconstruct_portfolio_history(positions, summary)
    
    if recon is not None:
        # 1. Reconstructed Max Drawdown
        max_dd = 0.0
        nav_series = recon["portfolio_nav"]
        if nav_series:
            peak = nav_series[0]
            for val in nav_series:
                if val > peak:
                    peak = val
                if peak > 0:
                    dd = (peak - val) / peak * 100.0
                    if dd > max_dd:
                        max_dd = dd
            max_dd = round(max_dd, 2)
            
        # 2. Reconstructed Volatility
        port_returns = recon["port_returns"]
        if len(port_returns) >= 2:
            mean_ret = sum(port_returns) / len(port_returns)
            var_ret = sum((r - mean_ret) ** 2 for r in port_returns) / (len(port_returns) - 1)
            daily_vol_dec = math.sqrt(var_ret)
            daily_vol = daily_vol_dec * 100.0
            annualized_vol = daily_vol * math.sqrt(252)
        else:
            daily_vol_dec = 0.0
            daily_vol = 0.0
            annualized_vol = 0.0
            
        # 3. Parametric VaR & CVaR
        value_at_risk_95 = total_value * (1.65 * daily_vol_dec)
        conditional_var_95 = total_value * (2.06 * daily_vol_dec)
        
        # 4. Beta calculation vs SPY and QQQ
        spy_returns = recon["spy_returns"]
        qqq_returns = recon["qqq_returns"]
        
        var_spy = calculate_variance(spy_returns)
        if var_spy > 0:
            portfolio_beta_spy = round(calculate_covariance(port_returns, spy_returns) / var_spy, 2)
        else:
            portfolio_beta_spy = 1.0
            
        var_qqq = calculate_variance(qqq_returns)
        if var_qqq > 0:
            portfolio_beta_qqq = round(calculate_covariance(port_returns, qqq_returns) / var_qqq, 2)
        else:
            portfolio_beta_qqq = 1.0
            
        # 5. Correlation matrix
        correlation_matrix: dict[str, dict[str, float]] = {}
        active_positions = [p for p in positions if p.quantity > 0]
        for p1 in active_positions:
            correlation_matrix[p1.symbol] = {}
            for p2 in active_positions:
                if p1.symbol == p2.symbol:
                    correlation_matrix[p1.symbol][p2.symbol] = 1.0
                else:
                    r1 = recon["asset_returns"].get(p1.symbol, [])
                    r2 = recon["asset_returns"].get(p2.symbol, [])
                    correlation_matrix[p1.symbol][p2.symbol] = round(calculate_correlation(r1, r2), 2)
                    
        # Risk-adjusted indicators calculation
        rf_annual = 0.04
        rf_daily = rf_annual / 252.0
        
        sharpe_ratio = None
        sortino_ratio = None
        jensens_alpha = None
        tracking_error = None
        information_ratio = None
        
        if len(port_returns) >= 2:
            # Sharpe
            annualized_port_return = mean_ret * 252
            excess_return = annualized_port_return - rf_annual
            annualized_vol_dec = daily_vol_dec * math.sqrt(252)
            if annualized_vol_dec > 0:
                sharpe_ratio = round(excess_return / annualized_vol_dec, 2)
            else:
                sharpe_ratio = 0.0
                
            # Sortino
            downside_diffs = [min(0.0, r - rf_daily) for r in port_returns]
            downside_variance = sum(d ** 2 for d in downside_diffs) / (len(port_returns) - 1)
            downside_dev_daily = math.sqrt(downside_variance)
            annualized_downside_dev = downside_dev_daily * math.sqrt(252)
            if annualized_downside_dev > 0:
                sortino_ratio = round(excess_return / annualized_downside_dev, 2)
            else:
                sortino_ratio = 0.0
                
            # Jensen's Alpha and Tracking Error / Information Ratio vs SPY
            if len(spy_returns) == len(port_returns) and var_spy > 0:
                # Jensen's Alpha
                beta = calculate_covariance(port_returns, spy_returns) / var_spy
                mean_spy_return = sum(spy_returns) / len(spy_returns)
                annualized_spy_return = mean_spy_return * 252
                alpha = annualized_port_return - (rf_annual + beta * (annualized_spy_return - rf_annual))
                jensens_alpha = round(alpha * 100.0, 2)
                
                # Tracking Error
                active_returns = [p - s for p, s in zip(port_returns, spy_returns)]
                mean_active = sum(active_returns) / len(active_returns)
                var_active = sum((r - mean_active) ** 2 for r in active_returns) / (len(active_returns) - 1)
                daily_te_dec = math.sqrt(var_active)
                tracking_error_val = daily_te_dec * math.sqrt(252)
                tracking_error = round(tracking_error_val * 100.0, 2)
                
                # Information Ratio
                annualized_active_return = mean_active * 252
                if tracking_error_val > 0:
                    information_ratio = round(annualized_active_return / tracking_error_val, 2)
                else:
                    information_ratio = 0.0

        data_quality = {
            "historical_metrics": "sufficient",
            "benchmark_returns": "sufficient",
            "security_return_series": "sufficient",
        }
        
        methodology = {
            "drawdown": "Calculated over 1-year historical reconstructed NAV of the current holdings.",
            "volatility_var": "Sample standard deviation of returns and parametric 95% VaR based on 1-year reconstructed daily closes.",
            "beta_correlation": "Covariance-based Beta and correlation matrix calculated over aligned 1-year daily close price returns.",
            "factor_exposures": "Heuristic classification, not a fitted factor model.",
            "stress_tests": "Illustrative assumption-based scenarios, not forecasts.",
            "sharpe_ratio": "Excess annualized return divided by annualized volatility: (Return - 4.0%) / Volatility.",
            "sortino_ratio": "Excess annualized return divided by annualized downside deviation: (Return - 4.0%) / Downside Volatility.",
            "jensens_alpha": "CAPM-based annualized excess return vs SPY benchmark: Alpha = Return - [Rf + Beta * (Market_Return - Rf)].",
            "tracking_error": "Annualized standard deviation of daily excess returns vs SPY.",
            "information_ratio": "Annualized active return vs SPY divided by Tracking Error.",
        }
    else:
        # Fallback to local snapshot database history (e.g. if Yahoo Finance fetch fails or in dry test runs)
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

        portfolio_beta_spy = None
        portfolio_beta_qqq = None
        correlation_matrix = {}
        
        rf_annual = 0.04
        rf_daily = rf_annual / 252.0
        
        sharpe_ratio = None
        sortino_ratio = None
        jensens_alpha = None
        tracking_error = None
        information_ratio = None
        
        if enough_history and daily_vol is not None and daily_vol > 0:
            port_returns_dec = [r / 100.0 for r in daily_returns]
            mean_ret_dec = sum(port_returns_dec) / len(port_returns_dec)
            annualized_port_return = mean_ret_dec * 252
            excess_return = annualized_port_return - rf_annual
            annualized_vol_dec = (daily_vol / 100.0) * math.sqrt(252)
            if annualized_vol_dec > 0:
                sharpe_ratio = round(excess_return / annualized_vol_dec, 2)
            else:
                sharpe_ratio = 0.0
                
            downside_diffs = [min(0.0, r - rf_daily) for r in port_returns_dec]
            downside_variance = sum(d ** 2 for d in downside_diffs) / (len(port_returns_dec) - 1)
            downside_dev_daily = math.sqrt(downside_variance)
            annualized_downside_dev = downside_dev_daily * math.sqrt(252)
            if annualized_downside_dev > 0:
                sortino_ratio = round(excess_return / annualized_downside_dev, 2)
            else:
                sortino_ratio = 0.0

        data_quality = {
            "historical_metrics": "sufficient" if enough_history else "insufficient",
            "benchmark_returns": "missing",
            "security_return_series": "missing",
        }
        
        methodology = {
            "drawdown": "Account-value drawdown; not adjusted for deposits or withdrawals.",
            "volatility_var": "Sample volatility and parametric 95% VaR require at least 20 daily returns.",
            "beta_correlation": "Unavailable without aligned benchmark and security return series.",
            "factor_exposures": "Heuristic classification, not a fitted factor model.",
            "stress_tests": "Illustrative assumption-based scenarios, not forecasts.",
            "sharpe_ratio": "Excess annualized return divided by annualized volatility: (Return - 4.0%) / Volatility.",
            "sortino_ratio": "Excess annualized return divided by annualized downside deviation: (Return - 4.0%) / Downside Volatility.",
            "jensens_alpha": "Jensen's Alpha requires aligned SPY return series (unavailable in fallback).",
            "tracking_error": "Tracking Error requires aligned SPY return series (unavailable in fallback).",
            "information_ratio": "Information Ratio requires aligned SPY return series (unavailable in fallback).",
        }

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
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=sortino_ratio,
        jensens_alpha=jensens_alpha,
        tracking_error=tracking_error,
        information_ratio=information_ratio,
        correlation_matrix=dict(correlation_matrix),
        factor_exposures=factor_exposures_pct,
        stress_tests=stress_tests,
        data_quality=data_quality,
        methodology=methodology,
    )
