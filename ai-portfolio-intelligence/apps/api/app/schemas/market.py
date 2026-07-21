"""Market intelligence contracts (plan §7)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RegimeState(str, Enum):
    RISK_ON_EXPANSION = "risk_on_expansion"
    RISK_ON_NARROWING = "risk_on_but_narrowing"
    TRENDING_DEFENSIVE = "trending_defensive"
    RANGE_BOUND = "range_bound"
    VOLATILITY_EXPANSION = "volatility_expansion"
    RISK_OFF_CONTRACTION = "risk_off_contraction"
    CRISIS_DISLOCATION = "crisis_or_dislocation"
    INSUFFICIENT_DATA = "insufficient_data"


class RegimeInputs(BaseModel):
    """Explainable dimensions. Any dimension may be None (unknown)."""

    trend: Optional[str] = None  # up | down | flat
    volatility: Optional[str] = None  # low | elevated | high | extreme
    breadth: Optional[str] = None  # broad | narrow | collapsing
    liquidity: Optional[str] = None  # ample | tightening | stressed
    rates: Optional[str] = None  # rising | falling | stable
    credit: Optional[str] = None  # tightening | stable | widening | blowout
    earnings_revisions: Optional[str] = None  # up | flat | down
    risk_appetite: Optional[str] = None  # risk_on | neutral | risk_off


class MarketRegime(BaseModel):
    label: RegimeState
    confidence: float
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    changed_dimensions: list[str] = Field(default_factory=list)
    previous_regime: Optional[RegimeState] = None
    transition_date: Optional[str] = None
    portfolio_implications: list[str] = Field(default_factory=list)
    data_limitations: list[str] = Field(default_factory=list)
    dimensions: RegimeInputs
    as_of: Optional[datetime] = None
    methodology: str = "rule_based_regime_v1"


class MarketIndicator(BaseModel):
    key: str
    label: str
    value: Optional[float] = None
    unit: Optional[str] = None
    status: str = "unavailable"  # available | unavailable | stale
    source: Optional[str] = None
    as_of: Optional[str] = None


class MarketSnapshot(BaseModel):
    as_of: Optional[datetime] = None
    indicators: list[MarketIndicator] = Field(default_factory=list)
    regime: Optional[MarketRegime] = None
    data_quality: dict[str, object] = Field(default_factory=dict)


class EconomicEvent(BaseModel):
    event_id: str
    name: str
    event_time: Optional[str] = None
    previous_value: Optional[str] = None
    consensus: Optional[str] = None
    actual_value: Optional[str] = None
    surprise: Optional[str] = None
    related_exposures: list[str] = Field(default_factory=list)
    source: Optional[str] = None
    provisional: bool = True
