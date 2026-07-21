"""Research notes contract (plan §8.5)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class NoteType(str, Enum):
    SECURITY = "security"
    EARNINGS = "earnings"
    MANAGEMENT = "management"
    INDUSTRY = "industry"
    MACRO = "macro"
    MEETING = "meeting"
    THESIS = "thesis"


class ResearchNote(BaseModel):
    note_id: str
    account_id: str
    instrument_id: Optional[str] = None
    symbol: Optional[str] = None
    note_type: NoteType = NoteType.SECURITY
    title: str = ""
    body: str = ""
    tags: list[str] = Field(default_factory=list)
    evidence_links: list[str] = Field(default_factory=list)
    version: int = 1
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ResearchNoteCreate(BaseModel):
    account_id: str
    instrument_id: Optional[str] = None
    symbol: Optional[str] = None
    note_type: NoteType = NoteType.SECURITY
    title: str = ""
    body: str = ""
    tags: list[str] = Field(default_factory=list)
    evidence_links: list[str] = Field(default_factory=list)
