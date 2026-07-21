"""Canonical instrument reference contract (plan §5 / §17 instruments table)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.domain.instrument import instrument_key


class InstrumentRecord(BaseModel):
    """A canonical, position-independent reference for a tradable security.

    The same record backs an owned holding, a watchlist name, a research
    candidate, a benchmark, an ETF, or a security with no current position.
    conId is authoritative when present; a symbol-only record is provisional.
    """

    instrument_id: str
    symbol: str
    con_id: Optional[int] = None
    name: Optional[str] = None
    asset_class: Optional[str] = None
    currency: Optional[str] = None
    exchange: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    is_etf: bool = False
    status: str = "active"
    provisional: bool = False
    aliases: list[str] = Field(default_factory=list)
    first_seen_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def build(
        cls,
        *,
        symbol: str,
        con_id: int | None = None,
        **kwargs,
    ) -> "InstrumentRecord":
        symbol_norm = (symbol or "").strip().upper()
        return cls(
            instrument_id=instrument_key(symbol_norm, con_id),
            symbol=symbol_norm,
            con_id=con_id,
            provisional=con_id is None,
            **kwargs,
        )


class InstrumentSearchResult(BaseModel):
    query: str
    count: int
    instruments: list[InstrumentRecord]
    data_quality: dict[str, object] = Field(
        default_factory=lambda: {"status": "available", "source": "local_instrument_master"}
    )


class InstrumentOverview(BaseModel):
    """Security-workspace Overview (plan §5.1) — works for owned and unowned names.

    Each section carries its own status so a missing sub-source degrades that
    section rather than fabricating a value or failing the whole page (§15.3).
    """

    instrument: InstrumentRecord
    position_status: str  # owned | not_owned
    market: dict[str, object]
    position: dict[str, object]
    decision: dict[str, object]
    data_quality: dict[str, object]

