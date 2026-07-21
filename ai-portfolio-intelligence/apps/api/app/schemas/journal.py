"""Trade journal + decision-learning contract (plan §10).

The journal evaluates the user's *process*, not trade frequency. Analytics are
descriptive; they never recommend trading more.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class OutcomeClassification(str, Enum):
    WIN_GOOD_PROCESS = "win_good_process"
    WIN_LUCKY = "win_lucky"
    LOSS_GOOD_PROCESS = "loss_good_process"
    LOSS_MISTAKE = "loss_mistake"
    SCRATCH = "scratch"
    OPEN = "open"


class ReviewInterval(str, Enum):
    IMMEDIATE = "immediate_post_execution"
    CATALYST = "catalyst"
    POSITION_CLOSE = "position_close"
    THIRTY_DAY = "thirty_day"
    QUARTERLY = "quarterly_process"
    CUSTOM = "custom"


class JournalReview(BaseModel):
    review_id: str
    interval: ReviewInterval
    note: str = ""
    rule_adherence: Optional[bool] = None
    lessons: list[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None


class JournalEntry(BaseModel):
    entry_id: str
    account_id: str
    instrument_id: str
    symbol: str

    trade_plan_id: Optional[str] = None
    decision_packet_id: Optional[str] = None
    thesis_version_id: Optional[str] = None

    entry_thesis: str = ""
    expected_catalyst: Optional[str] = None
    expected_holding_period: Optional[str] = None
    strategy: Optional[str] = None
    market_regime: Optional[str] = None
    confidence: Optional[str] = None

    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    position_size: Optional[float] = None
    planned_maximum_loss: Optional[float] = None
    max_adverse_excursion: Optional[float] = None
    max_favourable_excursion: Optional[float] = None
    realized_return: Optional[float] = None
    benchmark_relative_return: Optional[float] = None
    fees_and_fx: Optional[float] = None

    exit_reason: Optional[str] = None
    rule_adherence: Optional[bool] = None
    unplanned: bool = False
    data_readiness_failure: bool = False
    mistakes: list[str] = Field(default_factory=list)
    lessons: list[str] = Field(default_factory=list)
    outcome_classification: OutcomeClassification = OutcomeClassification.OPEN

    reviews: list[JournalReview] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None


class JournalEntryCreate(BaseModel):
    account_id: str
    instrument_id: str
    symbol: Optional[str] = None
    trade_plan_id: Optional[str] = None
    decision_packet_id: Optional[str] = None
    thesis_version_id: Optional[str] = None
    entry_thesis: str = ""
    expected_catalyst: Optional[str] = None
    expected_holding_period: Optional[str] = None
    strategy: Optional[str] = None
    confidence: Optional[str] = None
    entry_price: Optional[float] = None
    position_size: Optional[float] = None
    planned_maximum_loss: Optional[float] = None


class JournalEntryUpdate(BaseModel):
    exit_price: Optional[float] = None
    realized_return: Optional[float] = None
    benchmark_relative_return: Optional[float] = None
    max_adverse_excursion: Optional[float] = None
    max_favourable_excursion: Optional[float] = None
    fees_and_fx: Optional[float] = None
    exit_reason: Optional[str] = None
    rule_adherence: Optional[bool] = None
    unplanned: Optional[bool] = None
    mistakes: Optional[list[str]] = None
    lessons: Optional[list[str]] = None
    outcome_classification: Optional[OutcomeClassification] = None
    market_regime: Optional[str] = None
