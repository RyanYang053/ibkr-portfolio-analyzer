from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from app.services.portfolio.pnl_tracker import PortfolioPnLSnapshot


def _fetch_total_return_series(
    symbol: str,
    start_date: date,
    end_date: date,
    allow_mock: bool,
) -> tuple[dict[str, float], str]:
    from app.services.market_data.mock_provider import MockMarketDataProvider

    provider = MockMarketDataProvider(allow_mock=allow_mock)
    history = provider.get_historical_prices(symbol, start_date, end_date, total_return=True)
    series = {str(item["date"]): float(item["close"]) for item in history if item.get("close")}
    source = str(history[0].get("source", "unknown")) if history else "missing"
    return series, source


def _period_return(closes: dict[str, float], dates: list[str]) -> Optional[float]:
    usable = [closes[day] for day in dates if day in closes]
    if len(usable) < 2 or usable[0] <= 0:
        return None
    return (usable[-1] / usable[0]) - 1.0


def align_benchmark_comparison(
    history: list[PortfolioPnLSnapshot],
    portfolio_twr_percent: float | None,
    benchmark_symbols: list[str] | None = None,
    allow_mock: bool = False,
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

    result: dict[str, float | str | None] = {
        "period_start": dates[0],
        "period_end": dates[-1],
        "portfolio_twr_percent": portfolio_twr_percent,
        "aligned_observations": len(dates),
        "methodology": (
            "Benchmark total-return series are aligned to the same start and end dates as the portfolio "
            "measurement period and compared against cash-flow-adjusted portfolio TWR."
        ),
        "status": "missing",
    }

    if portfolio_twr_percent is None:
        result["methodology"] += " Excess return is withheld because portfolio TWR is unavailable."
        for symbol in benchmark_symbols:
            key = symbol.lower()
            result[f"{key}_return_percent"] = None
            result[f"{key}_excess_return_percent"] = None
            result[f"{key}_aligned_start"] = dates[0]
            result[f"{key}_aligned_end"] = dates[-1]
            result[f"{key}_source"] = None
            result[f"{key}_observations"] = 0
        return result

    any_benchmark = False
    for symbol in benchmark_symbols:
        key = symbol.lower()
        try:
            closes, source = _fetch_total_return_series(symbol, start, end, allow_mock=allow_mock)
        except Exception:
            closes, source = {}, "missing"

        aligned_dates = [day for day in dates if day in closes]
        benchmark_return = _period_return(closes, aligned_dates) if len(aligned_dates) >= 2 else None
        result[f"{key}_return_percent"] = (
            round(benchmark_return * 100.0, 4) if benchmark_return is not None else None
        )
        if benchmark_return is not None and portfolio_twr_percent is not None:
            result[f"{key}_excess_return_percent"] = round(portfolio_twr_percent - benchmark_return * 100.0, 4)
            any_benchmark = True
        else:
            result[f"{key}_excess_return_percent"] = None
        result[f"{key}_aligned_start"] = aligned_dates[0] if aligned_dates else None
        result[f"{key}_aligned_end"] = aligned_dates[-1] if aligned_dates else None
        result[f"{key}_source"] = source
        result[f"{key}_observations"] = len(aligned_dates)

    result["status"] = "sufficient" if any_benchmark else "missing"
    return result
