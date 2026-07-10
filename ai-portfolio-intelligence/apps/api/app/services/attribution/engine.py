from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from app.schemas.domain import AccountSummary, PerformanceAttribution, Position, utc_now
from app.services.portfolio.ledger_coverage import ledger_covers_period, load_ledger_coverage
from app.services.portfolio.pnl_tracker import PortfolioPnLSnapshot

SECTOR_BENCHMARK_ETF = {
    "Technology": "XLK",
    "Financials": "XLF",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Communication Services": "XLC",
    "Healthcare": "XLV",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Materials": "XLB",
    "Diversified": "SPY",
    "Unknown": "SPY",
}


def _sector_benchmark_return(sector: str, allow_mock: bool, period_start: date, period_end: date) -> Optional[float]:
    etf = SECTOR_BENCHMARK_ETF.get(sector, "SPY")
    try:
        from app.services.market_data.mock_provider import MockMarketDataProvider

        provider = MockMarketDataProvider(allow_mock=allow_mock)
        history = provider.get_historical_prices(etf, period_start, period_end, total_return=True)
        closes = {str(item["date"]): float(item["close"]) for item in history if item.get("close")}
        dates = sorted(closes)
        if len(dates) < 2 or closes[dates[0]] <= 0:
            return None
        return (closes[dates[-1]] / closes[dates[0]]) - 1.0
    except Exception:
        return None


def _portfolio_sector_weights(positions: list[Position], base_currency: str, fx_resolver) -> dict[str, float]:
    grouped: dict[str, float] = defaultdict(float)
    for position in positions:
        rate = fx_resolver(position.currency, base_currency)
        grouped[position.sector or "Unknown"] += abs(position.market_value * rate)
    total = sum(grouped.values())
    if total <= 0:
        return {}
    return {sector: weight / total for sector, weight in grouped.items()}


def _benchmark_sector_weights() -> dict[str, float]:
    return {
        "Technology": 0.30,
        "Financials": 0.13,
        "Healthcare": 0.12,
        "Consumer Cyclical": 0.10,
        "Communication Services": 0.09,
        "Industrials": 0.08,
        "Consumer Defensive": 0.06,
        "Energy": 0.04,
        "Utilities": 0.03,
        "Real Estate": 0.02,
        "Materials": 0.02,
        "Diversified": 0.01,
    }


def calculate_brinson_attribution(
    positions: list[Position],
    base_currency: str,
    fx_resolver,
    allow_mock: bool,
    portfolio_sector_returns: Optional[dict[str, float]] = None,
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
) -> tuple[Optional[float], Optional[float], Optional[float], Optional[float], dict[str, dict[str, float]], str]:
    if not portfolio_sector_returns:
        return (
            None,
            None,
            None,
            None,
            {},
            "Brinson attribution withheld: actual beginning-weight portfolio sector returns are unavailable.",
        )

    portfolio_weights = _portfolio_sector_weights(positions, base_currency, fx_resolver)
    benchmark_weights = _benchmark_sector_weights()
    sectors = sorted(set(portfolio_weights) | set(benchmark_weights))

    if period_start is None or period_end is None:
        period_end = date.today()
        period_start = period_end - timedelta(days=365)

    sector_benchmark_returns: dict[str, float] = {}
    for sector in sectors:
        sector_benchmark_returns[sector] = _sector_benchmark_return(sector, allow_mock, period_start, period_end) or 0.0

    allocation = 0.0
    selection = 0.0
    interaction = 0.0
    by_sector: dict[str, dict[str, float]] = {}

    for sector in sectors:
        w_p = portfolio_weights.get(sector, 0.0)
        w_b = benchmark_weights.get(sector, 0.0)
        r_p = portfolio_sector_returns.get(sector)
        r_b = sector_benchmark_returns.get(sector, 0.0)
        if r_p is None:
            continue
        alloc = (w_p - w_b) * r_b
        sel = w_b * (r_p - r_b)
        inter = (w_p - w_b) * (r_p - r_b)
        allocation += alloc
        selection += sel
        interaction += inter
        by_sector[sector] = {
            "portfolio_weight": round(w_p * 100.0, 2),
            "benchmark_weight": round(w_b * 100.0, 2),
            "portfolio_return_percent": round(r_p * 100.0, 2),
            "benchmark_return_percent": round(r_b * 100.0, 2),
            "allocation_effect_percent": round(alloc * 100.0, 2),
            "selection_effect_percent": round(sel * 100.0, 2),
            "interaction_effect_percent": round(inter * 100.0, 2),
        }

    if not by_sector:
        return (
            None,
            None,
            None,
            None,
            {},
            "Brinson attribution withheld: period-aligned portfolio sector returns are unavailable.",
        )

    total_active = allocation + selection + interaction
    methodology = (
        "Brinson-Fachler attribution uses beginning portfolio sector weights and period-aligned portfolio "
        "sector returns versus benchmark sector ETF total returns."
    )
    return (
        round(allocation * 100.0, 2),
        round(selection * 100.0, 2),
        round(interaction * 100.0, 2),
        round(total_active * 100.0, 2),
        by_sector,
        methodology,
    )


def calculate_performance_attribution(
    positions: list[Position],
    history: list[PortfolioPnLSnapshot],
    base_currency: str = "USD",
    fx_resolver=None,
    account_id: str | None = None,
) -> PerformanceAttribution:
    import sys

    from app.services.broker.ibkr_readonly import get_exchange_rate
    from app.services.portfolio.tax_lots import realized_gain_by_symbol
    from app.services.portfolio.transaction_store import get_transactions

    if fx_resolver is None:
        fx_resolver = get_exchange_rate

    tax_lot_realized: dict[str, float] = {}
    tax_lot_total: float | None = None
    tax_lot_status = "missing"
    if account_id:
        coverage = load_ledger_coverage(account_id)
        ordered = sorted(history, key=lambda item: (item.date, item.timestamp))
        period_start = date.fromisoformat(ordered[0].date) if ordered else None
        period_end = date.fromisoformat(ordered[-1].date) if ordered else None
        if coverage and ledger_covers_period(coverage, period_start, period_end) if period_start and period_end else False:
            transactions = get_transactions(account_id)
            tax_lot_realized = realized_gain_by_symbol(
                transactions,
                account_id,
                reporting_currency=base_currency,
                period_start=period_start,
                period_end=period_end,
            )
            if tax_lot_realized:
                tax_lot_total = round(sum(tax_lot_realized.values()), 2)
                tax_lot_status = "sufficient"

    security_selection: dict[str, float] = {}
    sector_allocation: dict[str, float] = defaultdict(float)
    asset_class_return: dict[str, float] = defaultdict(float)
    realized_val = 0.0
    unrealized_val = 0.0

    for pos in positions:
        pnl = pos.unrealized_pnl
        security_selection[pos.symbol] = round(pnl, 2)
        sector_name = pos.sector or "Unknown"
        sector_allocation[sector_name] += pnl

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

    sector_allocation_rounded = {key: round(value, 2) for key, value in sector_allocation.items()}
    asset_class_rounded = {key: round(value, 2) for key, value in asset_class_return.items()}

    benchmark_relative_alpha = None
    data_quality_benchmark = "missing"
    allow_mock = "pytest" in sys.modules

    allocation_effect = None
    selection_effect = None
    interaction_effect = None
    total_active_return = None
    brinson_by_sector: dict[str, dict[str, float]] = {}
    methodology = (
        "Current realized and unrealized P&L grouped by security, sector, and asset class. "
        "Brinson effects are withheld unless period-aligned portfolio sector returns are available."
    )

    if positions:
        net_liq = sum(abs(p.market_value) for p in positions)
        cash = history[-1].cash if history else 0.0
        summary = AccountSummary(
            account_id="all",
            net_liquidation=net_liq + cash,
            cash=cash,
            buying_power=0.0,
            margin_requirement=0.0,
            excess_liquidity=0.0,
            total_unrealized_pnl=sum(p.unrealized_pnl for p in positions),
            total_realized_pnl=sum(p.realized_pnl for p in positions),
            base_currency=base_currency,
            data_timestamp=utc_now(),
        )

        from app.services.risk.history_reconstructor import (
            calculate_covariance,
            calculate_variance,
            reconstruct_portfolio_history,
        )

        recon = None
        if "pytest" not in sys.modules:
            recon = reconstruct_portfolio_history(positions, summary)
        if recon is not None:
            port_returns = recon["port_returns"]
            spy_returns = recon["spy_returns"]
            var_spy = calculate_variance(spy_returns)
            if var_spy > 0:
                beta_spy = calculate_covariance(port_returns, spy_returns) / var_spy
                nav_series = recon["portfolio_nav"]
                if nav_series and spy_returns and nav_series[0] > 0:
                    p_ret = (nav_series[-1] - nav_series[0]) / nav_series[0]
                    spy_compounded = 1.0
                    for daily_return in spy_returns:
                        spy_compounded *= 1.0 + daily_return
                    spy_ret = spy_compounded - 1.0
                    rf = 0.04
                    alpha = p_ret - (rf + beta_spy * (spy_ret - rf))
                    benchmark_relative_alpha = round(alpha * 100.0, 2)
                    data_quality_benchmark = "sufficient"

        alloc, sel, inter, active, by_sector, brinson_methodology = calculate_brinson_attribution(
            positions,
            base_currency,
            fx_resolver,
            allow_mock=allow_mock,
            portfolio_sector_returns=None,
        )
        if by_sector:
            allocation_effect = alloc
            selection_effect = sel
            interaction_effect = inter
            total_active_return = active
            brinson_by_sector = by_sector
            methodology = brinson_methodology

    cash_flow_status = "missing"
    if account_id:
        coverage = load_ledger_coverage(account_id)
        ordered = sorted(history, key=lambda item: (item.date, item.timestamp))
        if ordered and coverage:
            period_start = date.fromisoformat(ordered[0].date)
            period_end = date.fromisoformat(ordered[-1].date)
            if ledger_covers_period(coverage, period_start, period_end):
                cash_flow_status = "sufficient"
            elif coverage.execution_only:
                cash_flow_status = "partial_execution_only"

    return PerformanceAttribution(
        security_selection_return=security_selection,
        sector_allocation_return=sector_allocation_rounded,
        asset_class_return=asset_class_rounded,
        realized_vs_unrealized={
            "realized": round(realized_val, 2),
            "unrealized": round(unrealized_val, 2),
        },
        benchmark_relative_alpha=benchmark_relative_alpha,
        allocation_effect=allocation_effect,
        selection_effect=selection_effect,
        interaction_effect=interaction_effect,
        total_active_return=total_active_return,
        brinson_by_sector=brinson_by_sector,
        tax_lot_realized_by_symbol=tax_lot_realized,
        tax_lot_total_realized=tax_lot_total,
        data_quality={
            "benchmark_data": data_quality_benchmark,
            "cash_flow_adjustment": cash_flow_status,
            "brinson_attribution": "sufficient" if brinson_by_sector else "insufficient",
            "tax_lot_realized": tax_lot_status,
        },
        methodology=methodology,
    )
