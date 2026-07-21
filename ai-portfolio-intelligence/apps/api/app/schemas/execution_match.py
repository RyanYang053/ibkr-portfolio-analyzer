"""Imported-execution matching contract (plan §9.4).

Matches completed broker executions to a Trade Plan. An unmatched execution is
NEVER assumed to have been recommended by the system.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class MatchType(str, Enum):
    PLANNED = "planned_execution"
    UNPLANNED = "unplanned_execution"
    PARTIAL_FILL = "partial_fill"
    MULTIPLE_FILLS = "multiple_fills"
    ADDED = "added_position"
    REDUCED = "reduced_position"
    CLOSED = "closed_position"
    OPTION_ASSIGNMENT = "option_assignment"
    OPTION_EXERCISE = "option_exercise"
    CORPORATE_ACTION = "corporate_action"
    NO_MATCH = "no_match"


class ExecutionMatch(BaseModel):
    match_id: str
    trade_plan_id: str
    account_id: str
    instrument_id: str
    symbol: str
    match_types: list[MatchType] = Field(default_factory=list)
    matched: bool = False
    transaction_ids: list[str] = Field(default_factory=list)
    planned_quantity: Optional[float] = None
    executed_quantity: float = 0.0
    # The system never assumes an imported transaction was one it recommended.
    assumed_recommended: bool = False
    notes: list[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None
