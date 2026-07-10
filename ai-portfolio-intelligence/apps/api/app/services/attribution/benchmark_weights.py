from __future__ import annotations

from datetime import date

from app.services.attribution.engine import SECTOR_BENCHMARK_ETF


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


def benchmark_sector_weights_as_of(as_of: date, *, allow_mock: bool = False) -> dict[str, float] | None:
    """Return documented static benchmark sector weights for demo/testing only.

    ETF share prices are not valid market-cap proxies. Production attribution must use
    licensed constituent weights or withhold Brinson numerics.
    """
    _ = (as_of, SECTOR_BENCHMARK_ETF)
    if not allow_mock:
        return None
    return _static_benchmark_sector_weights()
