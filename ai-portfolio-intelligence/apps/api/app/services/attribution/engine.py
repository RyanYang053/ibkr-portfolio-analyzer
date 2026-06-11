from collections import defaultdict
from typing import Any
from app.schemas.domain import (
    PerformanceAttribution,
    Position
)
from app.services.portfolio.pnl_tracker import PortfolioPnLSnapshot

def calculate_performance_attribution(
    positions: list[Position],
    history: list[PortfolioPnLSnapshot]
) -> PerformanceAttribution:
    """Analyze portfolio performance over time and attribute returns to security, sector, and asset class."""
    
    security_selection: dict[str, float] = {}
    sector_allocation: dict[str, float] = defaultdict(float)
    asset_class_return: dict[str, float] = defaultdict(float)
    realized_val = 0.0
    unrealized_val = 0.0
    
    # Calculate absolute contributions from current positions
    for pos in positions:
        pnl = pos.unrealized_pnl
        security_selection[pos.symbol] = round(pnl, 2)
        
        # Sector contribution
        sector_name = pos.sector or "Unknown"
        sector_allocation[sector_name] += pnl
        
        # Asset class contribution
        aclass = "Single Stock"
        if pos.is_etf:
            aclass = "ETF"
        elif pos.asset_class == "OPT":
            aclass = "Options"
        elif "BND" in pos.asset_class or "BOND" in pos.asset_class:
            aclass = "Bonds"
        asset_class_return[aclass] += pnl
        
        realized_val += pos.realized_pnl
        unrealized_val += pos.unrealized_pnl

    # Compute sector and asset class rounded values
    sector_allocation_rounded = {k: round(v, 2) for k, v in sector_allocation.items()}
    asset_class_rounded = {k: round(v, 2) for k, v in asset_class_return.items()}

    return PerformanceAttribution(
        security_selection_return=security_selection,
        sector_allocation_return=sector_allocation_rounded,
        asset_class_return=asset_class_rounded,
        realized_vs_unrealized={
            "realized": round(realized_val, 2),
            "unrealized": round(unrealized_val, 2)
        },
        benchmark_relative_alpha=None,
        data_quality={
            "benchmark_data": "missing",
            "cash_flow_adjustment": "missing",
        },
        methodology=(
            "Current realized and unrealized P&L grouped by security, sector, and asset class. "
            "This is not return attribution; benchmark alpha is withheld until aligned benchmark "
            "returns and cash-flow-adjusted portfolio returns are available."
        ),
    )
