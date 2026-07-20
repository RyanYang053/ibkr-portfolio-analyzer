"""Benchmark evidence labels for personal attribution disclosures."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.product_scope import ATTRIBUTION_DISCLAIMER
from app.services.attribution.proxy_sector_attribution import AttributionMethodology


@dataclass(frozen=True)
class BenchmarkEvidence:
    methodology: AttributionMethodology
    proxy_symbols: tuple[str, ...]
    fx_treatment: str
    weights_reconciled: bool
    residual_disclosed: bool
    official_constituent_level: bool = False
    disclaimer: str = ATTRIBUTION_DISCLAIMER


def personal_benchmark_evidence(
    *,
    proxy_symbols: tuple[str, ...],
    fx_treatment: str,
    weights_reconciled: bool,
    residual_disclosed: bool,
    methodology: AttributionMethodology = AttributionMethodology.SECTOR_ETF_PROXY,
) -> BenchmarkEvidence:
    return BenchmarkEvidence(
        methodology=methodology,
        proxy_symbols=proxy_symbols,
        fx_treatment=fx_treatment,
        weights_reconciled=weights_reconciled,
        residual_disclosed=residual_disclosed,
        official_constituent_level=False,
    )
