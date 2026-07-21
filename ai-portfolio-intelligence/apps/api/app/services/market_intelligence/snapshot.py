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


def derive_portfolio_proxy_dimensions(summary: object, positions: list) -> tuple[RegimeInputs, list[str]]:
    """Derive regime dimensions from the portfolio's own holdings.

    This is an EXPLICIT proxy (labeled ``portfolio_proxy``), not true market breadth —
    a real multi-asset provider would replace it. Values come from actual position
    P&L and cash, never fabricated.
    """
    equities = [p for p in positions if getattr(p, "asset_class", None) not in {"OPT", "FOP", "CASH"}]
    if len(equities) < 3:
        return RegimeInputs(), ["insufficient_holdings_for_proxy"]

    positive = sum(1 for p in equities if float(getattr(p, "unrealized_pnl", 0) or 0) > 0)
    frac_positive = positive / len(equities)
    trend = "up" if frac_positive >= 0.6 else "down" if frac_positive <= 0.4 else "flat"
    breadth = "broad" if frac_positive >= 0.6 else "narrow" if frac_positive < 0.5 else "broad"

    net_liq = float(getattr(summary, "net_liquidation", 0) or 0)
    cash = float(getattr(summary, "cash", 0) or 0)
    cash_pct = (cash / net_liq) if net_liq else 0.0
    risk_appetite = "risk_off" if cash_pct >= 0.25 else "risk_on" if cash_pct <= 0.05 else "neutral"

    dims = RegimeInputs(trend=trend, breadth=breadth, risk_appetite=risk_appetite)
    return dims, ["portfolio_proxy", "market_breadth_and_volatility_require_a_market_data_provider"]


def derive_dimensions(
    *,
    demo: bool,
    provided: dict | None = None,
    summary: object | None = None,
    positions: list | None = None,
) -> tuple[RegimeInputs, list[str]]:
    """Return (dimensions, limitations)."""
    if provided:
        return RegimeInputs(**{k: v for k, v in provided.items() if v}), []
    if demo:
        return _demo_dimensions(), ["demo_synthetic_dimensions"]
    if summary is not None and positions:
        return derive_portfolio_proxy_dimensions(summary, positions)
    # No configured multi-asset market data source and no portfolio: classify as unknown.
    return RegimeInputs(), ["no_market_data_provider_configured"]


def build_market_snapshot(
    *,
    demo: bool,
    provided_dimensions: dict | None = None,
    previous: MarketRegime | None = None,
    summary: object | None = None,
    positions: list | None = None,
) -> MarketSnapshot:
    now = datetime.now(timezone.utc)
    dims, limitations = derive_dimensions(
        demo=demo, provided=provided_dimensions, summary=summary, positions=positions
    )
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
