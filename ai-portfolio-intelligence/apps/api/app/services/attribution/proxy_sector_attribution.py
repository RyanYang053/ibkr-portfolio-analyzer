"""Proxy-based sector attribution for personal analytics."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.core.product_scope import ATTRIBUTION_DISCLAIMER


class AttributionMethodology(StrEnum):
    SECTOR_ETF_PROXY = "sector_etf_proxy"
    CURRENT_HOLDINGS_EXPOSURE = "current_holdings_exposure"
    LICENSED_POINT_IN_TIME_BRINSON = "licensed_point_in_time_brinson"


@dataclass(frozen=True)
class SectorAttributionEffect:
    sector: str
    portfolio_weight: Decimal
    proxy_weight: Decimal
    portfolio_return: Decimal
    proxy_return: Decimal
    allocation_effect: Decimal
    selection_like_effect: Decimal


@dataclass(frozen=True)
class ProxySectorAttributionResult:
    methodology: AttributionMethodology
    benchmark_proxy: str
    effects: tuple[SectorAttributionEffect, ...]
    residual: Decimal
    disclaimer: str = ATTRIBUTION_DISCLAIMER

    @property
    def is_official_brinson(self) -> bool:
        return False


def validate_weights(
    sectors: tuple[tuple[str, Decimal, Decimal, Decimal, Decimal], ...],
    *,
    tolerance: Decimal = Decimal("0.0001"),
) -> None:
    portfolio_weight = sum((row[1] for row in sectors), Decimal("0"))
    proxy_weight = sum((row[2] for row in sectors), Decimal("0"))

    if abs(portfolio_weight - Decimal("1")) > tolerance:
        raise ValueError("Portfolio sector weights do not reconcile to 100%")

    if abs(proxy_weight - Decimal("1")) > tolerance:
        raise ValueError("Proxy sector weights do not reconcile to 100%")

    names = [row[0] for row in sectors]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate sector records are not allowed")


def compute_proxy_sector_attribution(
    *,
    sectors: tuple[tuple[str, Decimal, Decimal, Decimal, Decimal], ...],
    benchmark_proxy: str = "SPY",
    methodology: AttributionMethodology = AttributionMethodology.SECTOR_ETF_PROXY,
) -> ProxySectorAttributionResult:
    """Approximate allocation / selection-like effects using sector proxies.

    Each sector tuple is:
    (name, portfolio_weight, proxy_weight, portfolio_return, proxy_return)
    """
    if methodology == AttributionMethodology.LICENSED_POINT_IN_TIME_BRINSON:
        raise ValueError(
            "licensed_point_in_time_brinson is disabled until an approved "
            "licensed provider is configured"
        )

    validate_weights(sectors)

    effects: list[SectorAttributionEffect] = []
    total_alloc = Decimal("0")
    total_select = Decimal("0")
    for name, p_w, b_w, p_r, b_r in sectors:
        allocation = (p_w - b_w) * b_r
        selection = p_w * (p_r - b_r)
        effects.append(
            SectorAttributionEffect(
                sector=name,
                portfolio_weight=p_w,
                proxy_weight=b_w,
                portfolio_return=p_r,
                proxy_return=b_r,
                allocation_effect=allocation,
                selection_like_effect=selection,
            )
        )
        total_alloc += allocation
        total_select += selection

    portfolio_return = sum((p_w * p_r for _, p_w, _, p_r, _ in sectors), Decimal("0"))
    proxy_return = sum((b_w * b_r for _, _, b_w, _, b_r in sectors), Decimal("0"))
    residual = portfolio_return - proxy_return - total_alloc - total_select

    return ProxySectorAttributionResult(
        methodology=methodology,
        benchmark_proxy=benchmark_proxy,
        effects=tuple(effects),
        residual=residual,
    )
