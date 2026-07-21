"""Market snapshot assembly (plan §7.1).

Indicators are marked ``unavailable`` unless a data source supplies them — the
snapshot never fabricates index/rate/vol levels. Regime dimensions are derived
from available data; in demo mode a representative, explicitly-synthetic set is
used so the UI can be exercised.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.market import (
    MarketIndicator,
    MarketRegime,
    MarketSnapshot,
    RegimeInputs,
)
from app.services.market_intelligence.regime import classify_regime

_INDICATOR_CATALOG = [
    ("equity_index_sp500", "S&P 500", "index"),
    ("equity_index_nasdaq", "Nasdaq 100", "index"),
    ("govt_yield_10y", "10Y Government Yield", "percent"),
    ("yield_curve_2s10s", "2s10s Slope", "bps"),
    ("credit_spread_ig", "IG Credit Spread", "bps"),
    ("volatility_vix", "Volatility Index", "level"),
    ("currency_dxy", "USD Index", "level"),
    ("commodity_oil", "Crude Oil", "usd"),
    ("breadth_adv_dec", "Advance/Decline", "ratio"),
]


def _demo_dimensions() -> RegimeInputs:
    return RegimeInputs(
        trend="up",
        volatility="low",
        breadth="broad",
        liquidity="ample",
        rates="stable",
        credit="tightening",
        earnings_revisions="up",
        risk_appetite="risk_on",
    )


def derive_dimensions(*, demo: bool, provided: dict | None = None) -> tuple[RegimeInputs, list[str]]:
    """Return (dimensions, limitations). Real derivation is wired when a provider exists."""
    if provided:
        return RegimeInputs(**{k: v for k, v in provided.items() if v}), []
    if demo:
        return _demo_dimensions(), ["demo_synthetic_dimensions"]
    # No configured multi-asset market data source: classify honestly as unknown.
    return RegimeInputs(), ["no_market_data_provider_configured"]


def build_market_snapshot(
    *,
    demo: bool,
    provided_dimensions: dict | None = None,
    previous: MarketRegime | None = None,
) -> MarketSnapshot:
    now = datetime.now(timezone.utc)
    dims, limitations = derive_dimensions(demo=demo, provided=provided_dimensions)
    regime = classify_regime(dims, previous=previous)
    regime.as_of = now
    for lim in limitations:
        if lim not in regime.data_limitations:
            regime.data_limitations.append(lim)

    indicators = [
        MarketIndicator(
            key=key,
            label=label,
            unit=unit,
            status="unavailable",
            source="demo" if demo else None,
        )
        for key, label, unit in _INDICATOR_CATALOG
    ]

    available = sum(1 for ind in indicators if ind.status == "available")
    return MarketSnapshot(
        as_of=now,
        indicators=indicators,
        regime=regime,
        data_quality={
            "status": "demo" if demo else "degraded",
            "available_indicators": available,
            "total_indicators": len(indicators),
            "note": "Market indicators require a configured data provider; unavailable ones are not fabricated.",
        },
    )
