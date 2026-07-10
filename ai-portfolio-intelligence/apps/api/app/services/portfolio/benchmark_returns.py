from __future__ import annotations

from bisect import bisect_right
from datetime import date, timedelta
from typing import Optional

from app.services.portfolio.pnl_tracker import PortfolioPnLSnapshot

MAX_ASOF_STALENESS_DAYS = 7


def _latest_daily_snapshots(history: list[PortfolioPnLSnapshot]) -> list[PortfolioPnLSnapshot]:
    by_date: dict[str, PortfolioPnLSnapshot] = {}
    for item in sorted(history, key=lambda row: (row.date, row.timestamp)):
        by_date[item.date] = item
    return [by_date[key] for key in sorted(by_date)]


def _fetch_total_return_series(
    symbol: str,
    start_date: date,
    end_date: date,
    allow_mock: bool,
) -> tuple[dict[str, float], str]:
    from app.services.market_data.mock_provider import MockMarketDataProvider

    provider = MockMarketDataProvider(allow_mock=allow_mock)
    history = provider.get_historical_prices(
        symbol,
        start_date - timedelta(days=MAX_ASOF_STALENESS_DAYS),
        end_date,
        total_return=True,
    )
    series = {
        str(item["date"]): float(item["close"])
        for item in history
        if item.get("close") is not None and float(item["close"]) > 0
    }
    source = str(history[0].get("source", "unknown")) if history else "missing"
    return series, source


def _asof_values(closes: dict[str, float], portfolio_dates: list[str]) -> list[tuple[str, str, float]]:
    """Map each portfolio date to the latest prior benchmark close without look-ahead."""
    market_dates = sorted(closes)
    if not market_dates:
        return []

    aligned: list[tuple[str, str, float]] = []
    for portfolio_day in portfolio_dates:
        index = bisect_right(market_dates, portfolio_day) - 1
        if index < 0:
            continue
        market_day = market_dates[index]
        stale_days = (date.fromisoformat(portfolio_day) - date.fromisoformat(market_day)).days
        if stale_days > MAX_ASOF_STALENESS_DAYS:
            continue
        aligned.append((portfolio_day, market_day, closes[market_day]))
    return aligned


def _period_return(values: list[tuple[str, str, float]]) -> Optional[float]:
    if len(values) < 2 or values[0][2] <= 0:
        return None
    return values[-1][2] / values[0][2] - 1.0


def align_benchmark_comparison(
    history: list[PortfolioPnLSnapshot],
    portfolio_twr_percent: float | None,
    benchmark_symbols: list[str] | None = None,
    allow_mock: bool = False,
) -> dict[str, float | str | None]:
    ordered = _latest_daily_snapshots(history)
    if not ordered:
        return {
            "status": "missing",
            "methodology": "No portfolio history available for benchmark alignment.",
        }

    benchmark_symbols = benchmark_symbols or ["SPY", "QQQ"]
    dates = [item.date for item in ordered]
    start = date.fromisoformat(dates[0])
    end = date.fromisoformat(dates[-1])

    result: dict[str, float | str | None] = {
        "period_start": dates[0],
        "period_end": dates[-1],
        "portfolio_twr_percent": portfolio_twr_percent,
        "aligned_observations": len(dates),
        "methodology": (
            "Benchmark adjusted-close/total-return series use as-of alignment to each portfolio snapshot date. "
            "Only the latest benchmark close on or before a snapshot is used; future prices are never backfilled. "
            "Excess return compares the benchmark period return with cash-flow-adjusted portfolio TWR."
        ),
        "status": "missing",
    }

    if portfolio_twr_percent is None:
        result["methodology"] += " Excess return is withheld because portfolio TWR is unavailable."
        for symbol in benchmark_symbols:
            key = symbol.lower()
            result[f"{key}_return_percent"] = None
            result[f"{key}_excess_return_percent"] = None
            result[f"{key}_aligned_start"] = None
            result[f"{key}_aligned_end"] = None
            result[f"{key}_source"] = None
            result[f"{key}_observations"] = 0
        return result

    any_benchmark = False
    for symbol in benchmark_symbols:
        key = symbol.lower()
        try:
            closes, source = _fetch_total_return_series(symbol, start, end, allow_mock=allow_mock)
            aligned = _asof_values(closes, dates)
        except Exception:
            source, aligned = "missing", []

        benchmark_return = _period_return(aligned)
        result[f"{key}_return_percent"] = (
            round(benchmark_return * 100.0, 4) if benchmark_return is not None else None
        )
        if benchmark_return is not None:
            result[f"{key}_excess_return_percent"] = round(
                portfolio_twr_percent - benchmark_return * 100.0,
                4,
            )
            any_benchmark = True
        else:
            result[f"{key}_excess_return_percent"] = None
        result[f"{key}_aligned_start"] = aligned[0][0] if aligned else None
        result[f"{key}_aligned_end"] = aligned[-1][0] if aligned else None
        result[f"{key}_source"] = source
        result[f"{key}_observations"] = len(aligned)

    result["status"] = "sufficient" if any_benchmark else "missing"
    return result
