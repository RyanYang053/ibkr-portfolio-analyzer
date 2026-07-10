from __future__ import annotations

from app.schemas.domain import Position


def instrument_key_from_position(position: Position) -> str:
    con_id = position.con_id if position.con_id is not None else -1
    return f"{position.symbol.upper()}:{con_id}"


def instrument_key_from_row(row: dict) -> str:
    symbol = str(row.get("symbol", "")).upper()
    con_id = row.get("con_id")
    return f"{symbol}:{int(con_id) if con_id is not None else -1}"
