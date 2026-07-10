from __future__ import annotations

from datetime import date, timedelta
from typing import Callable, Optional

from app.services.portfolio.pnl_tracker import PortfolioPnLSnapshot


def _fetch_close_series(
    symbol: str,
    start_date: date,
    end_date: date,
    allow_mock: bool,
) -> dict[str, float]:
    from app.services.market_data.mock_provider import MockMarketDataProvider

    provider = MockMarketDataProvider(allow_mock=allow_mock)
    history = provider.get_historical_prices(symbol, start_date, end_date)
    return {str(item["date"]): float(item["close"]) for item in history if item.get("close")}


def _period_return(closes: dict[str, float], dates: list[str]) -> Optional[float]:
    usable = [closes[day] for day in dates if day in closes]
    if len(usable) < 2 or usable[0] <= 0:
        return None
    return (usable[-1] / usable[0]) - 1.0


def align_benchmark_comparison(
    history: list[PortfolioPnLSnapshot],
    benchmark_symbols: list[str] | None = None,
    allow_mock: bool = True,
) -> dict[str, float | str | None]:
    if not history:
        return {
            "status": "missing",
            "methodology": "No portfolio history available for benchmark alignment.",
        }

    benchmark_symbols = benchmark_symbols or ["SPY", "QQQ"]
    ordered = sorted(history, key=lambda item: (item.date, item.timestamp))
    dates = [item.date for item in ordered]
    start = date.fromisoformat(dates[0])
    end = date.fromisoformat(dates[-1])
    fetch_start = start - timedelta(days=7)

    portfolio_nav = {item.date: item.net_liquidation for item in ordered}
    portfolio_dates = [day for day in dates if day in portfolio_nav]
    portfolio_return = _period_return(portfolio_nav, portfolio_dates)

    result: dict[str, float | str | None] = {
        "period_start": dates[0],
        "period_end": dates[-1],
        "portfolio_return_percent": round(portfolio_return * 100.0, 4) if portfolio_return is not None else None,
        "aligned_observations": len(portfolio_dates),
        "methodology": "Benchmark returns are aligned to portfolio snapshot dates using total price return.",
    }

    for symbol in benchmark_symbols:
        closes = _fetch_close_series(symbol, fetch_start, end, allow_mock=allow_mock)
        aligned_dates = [day for day in portfolio_dates if day in closes]
        if len(aligned_dates) < 2:
            result[f"{symbol.lower()}_return_percent"] = None
            result[f"{symbol.lower()}_excess_return_percent"] = None
            continue
        benchmark_return = _period_return(closes, aligned_dates)
        result[f"{symbol.lower()}_return_percent"] = (
            round(benchmark_return * 100.0, 4) if benchmark_return is not None else None
        )
        if portfolio_return is not None and benchmark_return is not None:
            result[f"{symbol.lower()}_excess_return_percent"] = round((portfolio_return - benchmark_return) * 100.0, 4)
        else:
            result[f"{symbol.lower()}_excess_return_percent"] = None

    result["status"] = "sufficient" if any(
        result.get("spy_return_percent") is not None or result.get("qqq_return_percent") is not None
        for _ in benchmark_symbols
    ) else "missing"
    return result
