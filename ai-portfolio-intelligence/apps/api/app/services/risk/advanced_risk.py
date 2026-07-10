from __future__ import annotations

import math
from bisect import bisect_right
from collections import defaultdict
from datetime import date, timedelta
from statistics import fmean
from typing import Any

from app.schemas.domain import AdvancedRiskMetrics, Position, StressScenario
from app.services.portfolio.pnl_tracker import PortfolioPnLSnapshot

TRADING_DAYS = 252
MIN_RISK_RETURNS = 20
Z_95 = 1.6448536269514722
NORMAL_ES_95 = 2.0627128075074253
MAX_BENCHMARK_STALENESS_DAYS = 7


def _latest_daily_snapshots(history: list[PortfolioPnLSnapshot]) -> list[PortfolioPnLSnapshot]:
    by_date: dict[str, PortfolioPnLSnapshot] = {}
    for item in sorted(history, key=lambda row: (row.date, row.timestamp)):
        if math.isfinite(float(item.net_liquidation)) and item.net_liquidation > 0:
            by_date[item.date] = item
    return [by_date[key] for key in sorted(by_date)]


def _sample_std(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = fmean(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(max(variance, 0.0))


def _max_drawdown_from_returns(returns: list[float]) -> float | None:
    if not returns:
        return None
    wealth = 1.0
    peak = 1.0
    maximum = 0.0
    for value in returns:
        if value <= -1.0 or not math.isfinite(value):
            return None
        wealth *= 1.0 + value
        peak = max(peak, wealth)
        maximum = max(maximum, (peak - wealth) / peak)
    return maximum * 100.0


def _actual_account_returns(
    summary: Any,
    history: list[PortfolioPnLSnapshot],
) -> tuple[list[float], list[str], str]:
    ordered = _latest_daily_snapshots(history)
    if len(ordered) < 2:
        return [], [item.date for item in ordered], "insufficient_history"

    from app.services.broker.ibkr_readonly import get_exchange_rate
    from app.services.portfolio.ledger_coverage import (
        external_cash_flows_for_interval,
        ledger_covers_period,
        load_ledger_coverage,
    )
    from app.services.portfolio.transaction_store import get_transactions

    account_id = str(getattr(summary, "account_id", "") or "default")
    period_start = date.fromisoformat(ordered[0].date)
    period_end = date.fromisoformat(ordered[-1].date)
    coverage = load_ledger_coverage(account_id)
    if not ledger_covers_period(coverage, period_start, period_end):
        if coverage and coverage.execution_only:
            status = "partial_execution_only"
        elif coverage:
            status = coverage.status
        else:
            status = "missing"
        return [], [item.date for item in ordered], status

    transactions = get_transactions(account_id)
    returns: list[float] = []
    dates = [item.date for item in ordered]
    for previous, current in zip(ordered, ordered[1:]):
        previous_date = date.fromisoformat(previous.date)
        current_date = date.fromisoformat(current.date)
        flow = external_cash_flows_for_interval(
            transactions,
            previous_date,
            current_date,
            summary.base_currency,
            get_exchange_rate,
        )
        value = (current.net_liquidation - flow) / previous.net_liquidation - 1.0
        if not math.isfinite(value) or value <= -1.0:
            return [], dates, "invalid_interval"
        returns.append(value)
    return returns, dates, "sufficient"


def _benchmark_returns_for_dates(
    symbol: str,
    dates: list[str],
    allow_mock: bool,
) -> tuple[list[float], str]:
    if len(dates) < 2:
        return [], "missing"

    from app.services.market_data.mock_provider import MockMarketDataProvider

    start = date.fromisoformat(dates[0]) - timedelta(days=MAX_BENCHMARK_STALENESS_DAYS)
    end = date.fromisoformat(dates[-1])
    rows = MockMarketDataProvider(allow_mock=allow_mock).get_historical_prices(
        symbol,
        start,
        end,
        total_return=True,
    )
    prices = {
        str(row["date"]): float(row["close"])
        for row in rows
        if row.get("close") is not None and float(row["close"]) > 0
    }
    source = str(rows[0].get("source", "unknown")) if rows else "missing"
    market_dates = sorted(prices)
    aligned: list[float] = []
    for portfolio_day in dates:
        index = bisect_right(market_dates, portfolio_day) - 1
        if index < 0:
            return [], source
        market_day = market_dates[index]
        staleness = (date.fromisoformat(portfolio_day) - date.fromisoformat(market_day)).days
        if staleness > MAX_BENCHMARK_STALENESS_DAYS:
            return [], source
        aligned.append(prices[market_day])
    returns = [current / previous - 1.0 for previous, current in zip(aligned, aligned[1:]) if previous > 0]
    return returns, source


def _covariance(x: list[float], y: list[float]) -> float | None:
    if len(x) < 2 or len(x) != len(y):
        return None
    mean_x = fmean(x)
    mean_y = fmean(y)
    return sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y)) / (len(x) - 1)


def _beta(portfolio_returns: list[float], benchmark_returns: list[float]) -> float | None:
    covariance = _covariance(portfolio_returns, benchmark_returns)
    variance = _covariance(benchmark_returns, benchmark_returns)
    if covariance is None or variance is None or variance <= 0:
        return None
    return covariance / variance


def _historical_metrics(
    returns: list[float],
    spy_returns: list[float],
    risk_free_rate_annual: float,
    total_value: float,
) -> dict[str, float | None]:
    result: dict[str, float | None] = {
        "max_drawdown": _max_drawdown_from_returns(returns),
        "volatility": None,
        "value_at_risk_95": None,
        "conditional_var_95": None,
        "historical_var_95": None,
        "sharpe_ratio": None,
        "sortino_ratio": None,
        "portfolio_beta_spy": None,
        "jensens_alpha": None,
        "tracking_error": None,
        "information_ratio": None,
    }
    if len(returns) < MIN_RISK_RETURNS:
        return result

    daily_mean = fmean(returns)
    daily_sigma = _sample_std(returns)
    if daily_sigma is None:
        return result

    annualized_return = (1.0 + daily_mean) ** TRADING_DAYS - 1.0 if daily_mean > -1.0 else -1.0
    annualized_sigma = daily_sigma * math.sqrt(TRADING_DAYS)
    result["volatility"] = annualized_sigma * 100.0

    # Parametric one-day normal loss estimates plus historical simulation quantile.
    var_loss_fraction = max(0.0, Z_95 * daily_sigma - daily_mean)
    es_loss_fraction = max(0.0, NORMAL_ES_95 * daily_sigma - daily_mean)
    result["value_at_risk_95"] = total_value * var_loss_fraction
    result["conditional_var_95"] = total_value * es_loss_fraction
    historical_losses = sorted(-value for value in returns)
    historical_index = max(0, min(len(historical_losses) - 1, int(math.ceil(0.05 * len(historical_losses))) - 1))
    result["historical_var_95"] = total_value * historical_losses[historical_index]

    if annualized_sigma > 0:
        result["sharpe_ratio"] = (annualized_return - risk_free_rate_annual) / annualized_sigma

    rf_daily = (1.0 + risk_free_rate_annual) ** (1.0 / TRADING_DAYS) - 1.0
    downside = [min(0.0, value - rf_daily) for value in returns]
    downside_sigma = math.sqrt(sum(value * value for value in downside) / len(downside)) * math.sqrt(TRADING_DAYS)
    if downside_sigma > 0:
        result["sortino_ratio"] = (annualized_return - risk_free_rate_annual) / downside_sigma

    if len(spy_returns) == len(returns) and len(spy_returns) >= MIN_RISK_RETURNS:
        beta = _beta(returns, spy_returns)
        result["portfolio_beta_spy"] = beta
        active_returns = [portfolio - benchmark for portfolio, benchmark in zip(returns, spy_returns)]
        tracking_daily = _sample_std(active_returns)
        benchmark_mean = fmean(spy_returns)
        benchmark_annual = (1.0 + benchmark_mean) ** TRADING_DAYS - 1.0 if benchmark_mean > -1.0 else -1.0
        if beta is not None:
            alpha = annualized_return - (
                risk_free_rate_annual + beta * (benchmark_annual - risk_free_rate_annual)
            )
            result["jensens_alpha"] = alpha * 100.0
        if tracking_daily is not None:
            tracking_annual = tracking_daily * math.sqrt(TRADING_DAYS)
            result["tracking_error"] = tracking_annual * 100.0
            if tracking_annual > 0:
                active_mean = fmean(active_returns)
                active_annual = (1.0 + active_mean) ** TRADING_DAYS - 1.0 if active_mean > -1.0 else -1.0
                result["information_ratio"] = active_annual / tracking_annual
    return result


def _factor_exposures(positions: list[Position], summary: Any) -> tuple[dict[str, float], list[str]]:
    from app.services.broker.ibkr_readonly import get_exchange_rate

    buckets: dict[str, float] = defaultdict(float)
    excluded: list[str] = []
    for position in positions:
        try:
            value = abs(position.market_value * get_exchange_rate(position.currency, summary.base_currency))
        except Exception:
            excluded.append(position.symbol)
            continue
        if position.is_speculative:
            buckets["Growth"] += value * 0.8
            buckets["Momentum"] += value * 0.2
        elif position.is_etf and position.symbol.upper() == "QQQ":
            buckets["Growth"] += value * 0.7
            buckets["Momentum"] += value * 0.3
        elif position.is_etf:
            buckets["Value"] += value * 0.5
            buckets["Low Volatility"] += value * 0.5
        elif position.sector in {"Technology", "Communication Services"}:
            buckets["Growth"] += value * 0.6
            buckets["Momentum"] += value * 0.4
        else:
            buckets["Value"] += value * 0.6
            buckets["Low Volatility"] += value * 0.4
    total = sum(buckets.values())
    if total <= 0:
        return {"Growth": 0.0, "Value": 0.0, "Momentum": 0.0, "Low Volatility": 0.0}, excluded
    return {key: round(value / total * 100.0, 2) for key, value in sorted(buckets.items())}, excluded


def _stress_tests(positions: list[Position], summary: Any, total_value: float) -> tuple[list[StressScenario], list[str]]:
    from app.services.broker.ibkr_readonly import get_exchange_rate

    scenarios = [
        ("Illustrative pandemic-style equity shock", "Broad equities -30%; speculative assets -45%.", -30.0, -45.0, -90.0),
        ("Illustrative inflation and rate shock", "Broad equities -20%; technology -33%; speculative assets -55%.", -20.0, -55.0, -75.0),
        ("Illustrative technology valuation shock", "Technology -75%; broad equities -50%; speculative assets -85%.", -50.0, -85.0, -95.0),
        ("Illustrative systemic credit shock", "Broad equities -45%; speculative assets -65%.", -45.0, -65.0, -85.0),
    ]
    results: list[StressScenario] = []
    excluded: list[str] = []
    for name, description, market_shock, speculative_shock, option_shock in scenarios:
        shock_value = 0.0
        for position in positions:
            try:
                base_value = position.market_value * get_exchange_rate(position.currency, summary.base_currency)
            except Exception:
                excluded.append(position.symbol)
                continue
            if position.asset_class in {"OPT", "FOP"}:
                shock = option_shock
            elif position.is_speculative:
                shock = speculative_shock
            elif position.sector == "Technology" or position.symbol.upper() == "QQQ":
                if "technology valuation" in name.lower():
                    shock = -75.0
                elif "inflation and rate" in name.lower():
                    shock = -33.0
                else:
                    shock = market_shock * 1.2
            else:
                shock = market_shock
            shock_value += base_value * max(-100.0, shock) / 100.0
        portfolio_change = shock_value / total_value * 100.0 if total_value > 0 else 0.0
        severity = "High" if abs(portfolio_change) > 25 else "Medium" if abs(portfolio_change) > 12 else "Low"
        results.append(
            StressScenario(
                name=name,
                description=description + " Assumption-based scenario, not a forecast or historical replay.",
                portfolio_change_pct=round(portfolio_change, 2),
                estimated_loss=round(abs(shock_value), 2),
                risk_level=severity,
            )
        )
    return results, sorted(set(excluded))


def calculate_advanced_risk_metrics(
    positions: list[Position],
    summary: Any,
    history: list[PortfolioPnLSnapshot],
) -> AdvancedRiskMetrics:
    """Calculate fail-closed historical risk plus explicitly labeled ex-ante diagnostics."""
    total_value = max(abs(float(summary.net_liquidation)), 1.0)
    from app.core.config import settings

    allow_mock = settings.broker_mode == "mock_ibkr_readonly"
    risk_free_rate = float(getattr(settings, "risk_free_rate_annual", 0.0))

    account_returns, snapshot_dates, ledger_status = _actual_account_returns(summary, history)
    try:
        spy_returns, spy_source = _benchmark_returns_for_dates("SPY", snapshot_dates, allow_mock)
    except Exception:
        spy_returns, spy_source = [], "missing"
    try:
        qqq_returns, qqq_source = _benchmark_returns_for_dates("QQQ", snapshot_dates, allow_mock)
    except Exception:
        qqq_returns, qqq_source = [], "missing"

    metrics = _historical_metrics(account_returns, spy_returns, risk_free_rate, total_value)
    beta_qqq = _beta(account_returns, qqq_returns) if len(account_returns) >= MIN_RISK_RETURNS else None

    correlation_matrix: dict[str, dict[str, float]] = {}
    modeled_coverage = 0.0
    modeled_excluded: list[str] = []
    try:
        from app.services.risk.history_reconstructor import calculate_correlation, reconstruct_portfolio_history

        reconstruction = reconstruct_portfolio_history(positions, summary, allow_mock=allow_mock)
        if reconstruction is not None:
            modeled_coverage = float(reconstruction.get("modeled_gross_coverage_percent", 0.0))
            modeled_excluded = list(reconstruction.get("excluded_symbols", []))
            symbols = list(reconstruction.get("modeled_symbols", []))
            asset_returns = reconstruction.get("asset_returns", {})
            for left in symbols:
                correlation_matrix[left] = {}
                for right in symbols:
                    correlation_matrix[left][right] = 1.0 if left == right else round(
                        calculate_correlation(asset_returns.get(left, []), asset_returns.get(right, [])),
                        4,
                    )
    except Exception:
        reconstruction = None

    factor_exposures, factor_excluded = _factor_exposures(positions, summary)
    stress_tests, stress_excluded = _stress_tests(positions, summary, total_value)

    enough_history = len(account_returns) >= MIN_RISK_RETURNS
    benchmark_sufficient = enough_history and len(spy_returns) == len(account_returns)
    current_holdings_quality = (
        "sufficient_modeled_current_holdings"
        if correlation_matrix and modeled_coverage >= 95.0
        else "partial_modeled_current_holdings"
        if correlation_matrix
        else "missing"
    )

    data_quality = {
        "historical_metrics": "sufficient" if enough_history else "insufficient",
        "cash_flow_ledger": ledger_status,
        "benchmark_returns": "sufficient" if benchmark_sufficient else "missing",
        "benchmark_spy_source": spy_source,
        "benchmark_qqq_source": qqq_source,
        "security_return_series": current_holdings_quality,
        "current_holdings_modeled_coverage_percent": f"{modeled_coverage:.2f}",
        "current_holdings_excluded_symbols": ",".join(sorted(set(modeled_excluded))) or "none",
        "stress_fx_excluded_symbols": ",".join(sorted(set(stress_excluded))) or "none",
        "factor_fx_excluded_symbols": ",".join(sorted(set(factor_excluded))) or "none",
    }

    methodology = {
        "drawdown": (
            "Maximum drawdown is calculated from the compounded cash-flow-adjusted account return series. "
            "It is withheld when the activity ledger does not cover the full snapshot period."
        ),
        "volatility_var": (
            f"Annualized sample volatility, parametric normal 95% VaR/ES, and historical-simulation 95% VaR "
            f"require at least {MIN_RISK_RETURNS} cash-flow-adjusted returns."
        ),
        "beta_correlation": (
            "Portfolio beta uses actual cash-flow-adjusted account returns aligned as-of to benchmark total returns. "
            "The security correlation matrix is a separate ex-ante current-holdings model and is not account history."
        ),
        "factor_exposures": "Heuristic current-exposure classification; not a fitted multi-factor regression.",
        "stress_tests": "Current base-currency market values under transparent assumption-based shocks; not forecasts.",
        "risk_free_rate": f"Configured annual risk-free rate: {risk_free_rate * 100.0:.4f}%.",
        "sharpe_ratio": "Geometrically annualized mean return minus configured risk-free rate, divided by annualized volatility.",
        "sortino_ratio": "Geometrically annualized mean return minus configured risk-free rate, divided by annualized downside deviation.",
        "jensens_alpha": "CAPM alpha from actual account returns and aligned SPY total returns.",
        "tracking_error": "Annualized sample standard deviation of actual account active returns versus SPY.",
        "information_ratio": "Geometrically annualized mean active return divided by annualized tracking error.",
    }

    def rounded(name: str, digits: int = 2):
        value = metrics.get(name)
        return round(float(value), digits) if value is not None and math.isfinite(float(value)) else None

    return AdvancedRiskMetrics(
        max_drawdown=rounded("max_drawdown"),
        volatility=rounded("volatility"),
        portfolio_beta_spy=rounded("portfolio_beta_spy"),
        portfolio_beta_qqq=round(beta_qqq, 2) if beta_qqq is not None else None,
        value_at_risk_95=rounded("value_at_risk_95"),
        conditional_var_95=rounded("conditional_var_95"),
        historical_var_95=rounded("historical_var_95"),
        sharpe_ratio=rounded("sharpe_ratio"),
        sortino_ratio=rounded("sortino_ratio"),
        jensens_alpha=rounded("jensens_alpha"),
        tracking_error=rounded("tracking_error"),
        information_ratio=rounded("information_ratio"),
        correlation_matrix=correlation_matrix,
        factor_exposures=factor_exposures,
        stress_tests=stress_tests,
        data_quality=data_quality,
        methodology=methodology,
    )
