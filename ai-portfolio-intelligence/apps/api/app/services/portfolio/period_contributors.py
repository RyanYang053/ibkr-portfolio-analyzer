from __future__ import annotations

from datetime import date

from app.services.portfolio.pnl_tracker import PortfolioPnLSnapshot


def period_position_contributors(
    history: list[PortfolioPnLSnapshot],
    *,
    limit: int = 3,
) -> tuple[list[str], list[str]]:
    """Rank symbols by selected-period unrealized PnL change between first and last snapshot."""
    ordered = sorted(history, key=lambda row: (row.date, row.timestamp))
    if len(ordered) < 2:
        return [], []

    opening = ordered[0]
    closing = ordered[-1]
    opening_by_symbol = {item.symbol: item for item in opening.positions}
    closing_by_symbol = {item.symbol: item for item in closing.positions}
    symbols = sorted(set(opening_by_symbol) | set(closing_by_symbol))

    changes: list[tuple[str, float]] = []
    for symbol in symbols:
        open_pnl = opening_by_symbol[symbol].unrealized_pnl if symbol in opening_by_symbol else 0.0
        close_pnl = closing_by_symbol[symbol].unrealized_pnl if symbol in closing_by_symbol else 0.0
        changes.append((symbol, float(close_pnl) - float(open_pnl)))

    contributors = [symbol for symbol, value in sorted(changes, key=lambda item: item[1], reverse=True) if value > 0][:limit]
    detractors = [symbol for symbol, value in sorted(changes, key=lambda item: item[1]) if value < 0][:limit]
    return contributors, detractors
