"""Canonical instrument identity — conId-first."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InstrumentId:
    """conId is authoritative when present; symbol-only keys are provisional."""

    symbol: str
    con_id: int | None = None
    currency: str | None = None
    exchange: str | None = None
    provisional: bool = False

    def __post_init__(self) -> None:
        symbol = (self.symbol or "").strip().upper()
        if not symbol:
            raise ValueError("Instrument symbol is required")
        object.__setattr__(self, "symbol", symbol)
        if self.con_id is None:
            object.__setattr__(self, "provisional", True)

    @property
    def key(self) -> str:
        return instrument_key(self.symbol, self.con_id)


def instrument_key(symbol: str, con_id: int | None = None) -> str:
    symbol_norm = (symbol or "").strip().upper()
    if con_id is not None:
        return f"{symbol_norm}:{int(con_id)}"
    return symbol_norm
