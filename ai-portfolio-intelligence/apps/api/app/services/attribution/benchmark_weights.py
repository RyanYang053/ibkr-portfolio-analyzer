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


def benchmark_sector_weights_as_of(
    as_of: date,
    *,
    allow_mock: bool = False,
    benchmark_id: str = "SPY",
) -> dict[str, float] | None:
    """Return licensed benchmark sector weights when persisted; demo static weights only in mock mode."""
    _ = SECTOR_BENCHMARK_ETF
    from app.db.benchmark_repo import list_benchmark_constituent_weights, sector_weights_from_constituents

    constituents = list_benchmark_constituent_weights(benchmark_id, as_of)
    if constituents:
        weights = sector_weights_from_constituents(constituents)
        return weights or None
    if allow_mock:
        return _static_benchmark_sector_weights()
    return None


def benchmark_weights_source(as_of: date, *, allow_mock: bool = False, benchmark_id: str = "SPY") -> str:
    from app.db.benchmark_repo import list_benchmark_constituent_weights

    if list_benchmark_constituent_weights(benchmark_id, as_of):
        return "licensed_constituent_weights"
    if allow_mock:
        return "demo_static_weights"
    return "unavailable"
