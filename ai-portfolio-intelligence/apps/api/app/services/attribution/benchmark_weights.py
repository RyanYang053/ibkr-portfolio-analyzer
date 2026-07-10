from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from app.services.attribution.engine import SECTOR_BENCHMARK_ETF


def _price_on_or_before(symbol: str, as_of: date, allow_mock: bool) -> Optional[float]:
    from app.services.market_data.mock_provider import MockMarketDataProvider

    provider = MockMarketDataProvider(allow_mock=allow_mock)
    history = provider.get_historical_prices(symbol.upper(), as_of - timedelta(days=10), as_of, total_return=True)
    closes = {str(item["date"]): float(item["close"]) for item in history if item.get("close")}
    if not closes:
        return None
    eligible = [day for day in closes if day <= as_of.isoformat()]
    if not eligible:
        return None
    return closes[sorted(eligible)[-1]]


def _static_benchmark_sector_weights() -> dict[str, float]:
    return {
        "Technology": 0.30,
        "Financials": 0.13,
        "Healthcare": 0.12,
        "Consumer Cyclical": 0.10,
        "Communication Services": 0.09,
        "Industrials": 0.08,
        "Consumer Defensive": 0.06,
        "Energy": 0.04,
        "Utilities": 0.03,
        "Real Estate": 0.02,
        "Materials": 0.02,
        "Diversified": 0.01,
    }


def benchmark_sector_weights_as_of(as_of: date, *, allow_mock: bool = False) -> dict[str, float]:
    """Derive date-aware benchmark sector weights from sector ETF price levels.

    ETF prices act as a relative market-cap proxy at ``as_of``. When prices are
    unavailable the static S&P-like allocation is used as a fallback.
    """
    static = _static_benchmark_sector_weights()
    proxy_values: dict[str, float] = {}
    for sector, etf in SECTOR_BENCHMARK_ETF.items():
        if sector in {"Unknown", "Diversified"}:
            continue
        price = _price_on_or_before(etf, as_of, allow_mock=allow_mock)
        if price is None or price <= 0:
            continue
        proxy_values[sector] = price * static.get(sector, 0.01)
    if not proxy_values:
        return static
    total = sum(proxy_values.values())
    if total <= 0:
        return static
    return {sector: value / total for sector, value in proxy_values.items()}
