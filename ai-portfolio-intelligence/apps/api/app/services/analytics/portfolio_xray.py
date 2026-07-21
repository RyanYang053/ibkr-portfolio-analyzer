"""Portfolio X-Ray: declarative, threshold-configurable diagnostic rules.

Complements :func:`app.services.risk.portfolio_risk.analyze_portfolio_risk` (which
already covers single-name, sector, speculative, cash-floor and gross-exposure limits)
with the diversification-shape checks it does not: currency concentration, top-5
concentration, holdings-count adequacy, and effective-holdings (inverse Herfindahl).

Each rule yields a Ghostfolio-style finding — a measured value against a user-tunable
threshold with a pass/warn status and a plain-language message. Deterministic and pure:
holdings in, findings out. Market values are taken in the account base currency.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Protocol, Sequence


class HoldingLike(Protocol):
    symbol: str
    market_value: float
    currency: str
    asset_class: str


@dataclass(frozen=True)
class XrayFinding:
    key: str
    label: str
    value: float | None
    threshold: float | None
    status: str  # "pass" | "warn" | "insufficient"
    detail: str


DEFAULT_THRESHOLDS: dict[str, float] = {
    "max_currency_weight_pct": 70.0,
    "max_top5_weight_pct": 60.0,
    "min_holdings": 10.0,
    "min_effective_holdings": 8.0,
}


def _gross_weights_pct(holdings: Sequence[HoldingLike], field: str) -> dict[str, float]:
    grouped: dict[str, float] = defaultdict(float)
    gross = sum(abs(h.market_value) for h in holdings)
    if gross <= 0:
        return {}
    for holding in holdings:
        grouped[str(getattr(holding, field) or "Unknown")] += abs(holding.market_value)
    return {key: value / gross * 100.0 for key, value in grouped.items()}


def _max_status(value: float, threshold: float) -> str:
    return "warn" if value > threshold else "pass"


def _min_status(value: float, threshold: float) -> str:
    return "warn" if value < threshold else "pass"


def portfolio_xray(
    holdings: Sequence[HoldingLike],
    *,
    thresholds: dict[str, float] | None = None,
) -> list[XrayFinding]:
    """Evaluate the X-Ray diagnostic rules against current holdings."""
    limits = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    priced = [h for h in holdings if abs(h.market_value) > 0]

    if not priced:
        return [
            XrayFinding(key, key.replace("_", " "), None, limits.get(key), "insufficient", "No priced holdings.")
            for key in ("currency_concentration", "top5_concentration", "holdings_count", "effective_holdings")
        ]

    findings: list[XrayFinding] = []

    currency_weights = _gross_weights_pct(priced, "currency")
    top_currency, top_currency_weight = max(currency_weights.items(), key=lambda kv: kv[1])
    threshold = limits["max_currency_weight_pct"]
    findings.append(
        XrayFinding(
            "currency_concentration",
            "Currency concentration",
            round(top_currency_weight, 2),
            threshold,
            _max_status(top_currency_weight, threshold),
            f"{top_currency} is {top_currency_weight:.1f}% of gross exposure (limit {threshold:.0f}%).",
        )
    )

    weights = sorted((abs(h.market_value) for h in priced), reverse=True)
    gross = sum(weights)
    top5_weight = sum(weights[:5]) / gross * 100.0
    threshold = limits["max_top5_weight_pct"]
    findings.append(
        XrayFinding(
            "top5_concentration",
            "Top-5 concentration",
            round(top5_weight, 2),
            threshold,
            _max_status(top5_weight, threshold),
            f"The 5 largest holdings are {top5_weight:.1f}% of gross exposure (limit {threshold:.0f}%).",
        )
    )

    holdings_count = float(len(priced))
    threshold = limits["min_holdings"]
    findings.append(
        XrayFinding(
            "holdings_count",
            "Holdings count",
            holdings_count,
            threshold,
            _min_status(holdings_count, threshold),
            f"{len(priced)} priced holdings (suggested minimum {threshold:.0f}).",
        )
    )

    fractions = [value / gross for value in weights]
    hhi = sum(fraction * fraction for fraction in fractions)
    effective = 1.0 / hhi if hhi > 0 else 0.0
    threshold = limits["min_effective_holdings"]
    findings.append(
        XrayFinding(
            "effective_holdings",
            "Effective holdings (1/HHI)",
            round(effective, 2),
            threshold,
            _min_status(effective, threshold),
            f"Effective number of holdings is {effective:.1f} (suggested minimum {threshold:.0f}).",
        )
    )

    return findings
