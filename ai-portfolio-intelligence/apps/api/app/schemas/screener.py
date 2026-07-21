"""Screener contracts (plan §8.2).

A screen surfaces research candidates — never a buy recommendation. Every result
carries the criteria it matched, the data it was missing, and a portfolio-fit
score, so the user decides what to research next.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FilterOp(str, Enum):
    GTE = "gte"
    LTE = "lte"
    GT = "gt"
    LT = "lt"
    EQ = "eq"


class ScreenFilter(BaseModel):
    field: str
    op: FilterOp
    value: float


class ScreenDefinition(BaseModel):
    screen_id: str
    name: str
    filters: list[ScreenFilter] = Field(default_factory=list)
    universe: str = "holdings_and_watchlist"  # holdings_and_watchlist | holdings | watchlist
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ScreenDefinitionCreate(BaseModel):
    name: str
    filters: list[ScreenFilter] = Field(default_factory=list)
    universe: str = "holdings_and_watchlist"


class ScreenResult(BaseModel):
    result_id: str
    symbol: str
    instrument_id: str
    rank: int
    matched_criteria: list[str] = Field(default_factory=list)
    failed_criteria: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    portfolio_fit: dict[str, object] = Field(default_factory=dict)
    research_ready: bool = False
    # A screen result is a research candidate, never a buy signal.
    is_buy_recommendation: bool = False


class ScreenRun(BaseModel):
    run_id: str
    screen_id: str
    account_id: str
    as_of: Optional[datetime] = None
    universe_size: int = 0
    results: list[ScreenResult] = Field(default_factory=list)
    data_quality: dict[str, object] = Field(default_factory=dict)
