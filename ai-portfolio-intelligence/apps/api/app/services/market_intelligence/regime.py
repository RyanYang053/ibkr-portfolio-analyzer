"""Explainable market-regime classifier (plan §7.2).

Deterministic and rule-based by design: the regime label is NEVER produced by an
LLM. Every classification exposes its supporting and contradicting evidence, its
confidence, and which dimensions were unavailable.
"""

from __future__ import annotations

from app.schemas.market import MarketRegime, RegimeInputs, RegimeState

_DIMENSIONS = (
    "trend",
    "volatility",
    "breadth",
    "liquidity",
    "rates",
    "credit",
    "earnings_revisions",
    "risk_appetite",
)

_MIN_KNOWN = 3

# Human-readable phrasing for evidence lines.
def _ev(dim: str, value: str) -> str:
    return f"{dim.replace('_', ' ')}={value}"


_IMPLICATIONS: dict[RegimeState, list[str]] = {
    RegimeState.RISK_ON_EXPANSION: [
        "Broad participation supports keeping core equity exposure.",
        "Trends are constructive; add-capacity checks still apply per position.",
    ],
    RegimeState.RISK_ON_NARROWING: [
        "Leadership is narrowing — concentration risk in the largest names rises.",
        "Favor breadth confirmation before adding to extended leaders.",
    ],
    RegimeState.TRENDING_DEFENSIVE: [
        "Up-trend with defensive leadership — quality and low-volatility factors favored.",
    ],
    RegimeState.RANGE_BOUND: [
        "No dominant trend — mean-reversion risk; avoid chasing breakouts.",
    ],
    RegimeState.VOLATILITY_EXPANSION: [
        "Rising volatility — position sizing should account for wider ranges.",
        "Options premia elevated; review short-option and gap exposure.",
    ],
    RegimeState.RISK_OFF_CONTRACTION: [
        "Down-trend with weakening credit — protect capital, review stops and liquidity.",
    ],
    RegimeState.CRISIS_DISLOCATION: [
        "Dislocation risk — prioritize liquidity, reconciliation, and data integrity over new risk.",
    ],
    RegimeState.INSUFFICIENT_DATA: [
        "Too few reliable market dimensions to classify a regime.",
    ],
}


def _match(inputs: RegimeInputs, dim: str, values: set[str]) -> bool:
    return getattr(inputs, dim) in values


def _classify_label(i: RegimeInputs) -> RegimeState:
    """Priority cascade — first matching rule wins (explainable ordering)."""
    if _match(i, "volatility", {"extreme"}) and (
        _match(i, "credit", {"blowout"}) or _match(i, "breadth", {"collapsing"})
    ):
        return RegimeState.CRISIS_DISLOCATION
    if _match(i, "trend", {"down"}) and (
        _match(i, "credit", {"widening", "blowout"}) or _match(i, "risk_appetite", {"risk_off"})
    ):
        return RegimeState.RISK_OFF_CONTRACTION
    if _match(i, "volatility", {"high", "extreme"}) and not _match(i, "trend", {"down"}):
        return RegimeState.VOLATILITY_EXPANSION
    if _match(i, "trend", {"up"}):
        if _match(i, "risk_appetite", {"risk_off", "neutral"}) and _match(i, "breadth", {"narrow", "collapsing"}):
            return RegimeState.TRENDING_DEFENSIVE
        if _match(i, "breadth", {"narrow", "collapsing"}):
            return RegimeState.RISK_ON_NARROWING
        return RegimeState.RISK_ON_EXPANSION
    if _match(i, "trend", {"flat"}):
        return RegimeState.RANGE_BOUND
    return RegimeState.RANGE_BOUND


# Each regime's "aligned" dimension values — used to derive supporting evidence.
_ALIGNED: dict[RegimeState, dict[str, set[str]]] = {
    RegimeState.RISK_ON_EXPANSION: {"trend": {"up"}, "breadth": {"broad"}, "volatility": {"low", "elevated"}, "risk_appetite": {"risk_on"}, "credit": {"tightening", "stable"}},
    RegimeState.RISK_ON_NARROWING: {"trend": {"up"}, "breadth": {"narrow", "collapsing"}},
    RegimeState.TRENDING_DEFENSIVE: {"trend": {"up"}, "risk_appetite": {"neutral", "risk_off"}, "breadth": {"narrow", "collapsing"}},
    RegimeState.RANGE_BOUND: {"trend": {"flat"}, "volatility": {"low", "elevated"}},
    RegimeState.VOLATILITY_EXPANSION: {"volatility": {"high", "extreme"}},
    RegimeState.RISK_OFF_CONTRACTION: {"trend": {"down"}, "credit": {"widening", "blowout"}, "risk_appetite": {"risk_off"}},
    RegimeState.CRISIS_DISLOCATION: {"volatility": {"extreme"}, "credit": {"blowout"}, "breadth": {"collapsing"}},
}


def classify_regime(inputs: RegimeInputs, *, previous: MarketRegime | None = None) -> MarketRegime:
    known = {d: getattr(inputs, d) for d in _DIMENSIONS if getattr(inputs, d) is not None}
    unknown = [d for d in _DIMENSIONS if getattr(inputs, d) is None]

    if len(known) < _MIN_KNOWN:
        return MarketRegime(
            label=RegimeState.INSUFFICIENT_DATA,
            confidence=0.0,
            data_limitations=[f"missing dimension: {d}" for d in unknown],
            portfolio_implications=_IMPLICATIONS[RegimeState.INSUFFICIENT_DATA],
            dimensions=inputs,
            previous_regime=previous.label if previous else None,
        )

    label = _classify_label(inputs)
    aligned = _ALIGNED.get(label, {})
    supporting = [_ev(d, v) for d, v in known.items() if d in aligned and v in aligned[d]]
    contradicting = [
        _ev(d, v) for d, v in known.items() if d in aligned and v not in aligned[d]
    ]
    confidence = round(len(supporting) / max(len(known), 1), 2)

    changed: list[str] = []
    if previous is not None:
        prev_dims = previous.dimensions
        changed = [d for d in _DIMENSIONS if getattr(prev_dims, d) != getattr(inputs, d) and getattr(inputs, d) is not None]

    return MarketRegime(
        label=label,
        confidence=confidence,
        supporting_evidence=supporting,
        contradicting_evidence=contradicting,
        changed_dimensions=changed,
        previous_regime=previous.label if previous else None,
        portfolio_implications=_IMPLICATIONS.get(label, []),
        data_limitations=[f"missing dimension: {d}" for d in unknown],
        dimensions=inputs,
    )
