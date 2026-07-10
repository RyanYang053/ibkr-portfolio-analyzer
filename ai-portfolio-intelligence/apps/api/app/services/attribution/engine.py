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


def _benchmark_sector_weights(period_start: date | None = None, *, allow_mock: bool = False) -> dict[str, float] | None:
    from app.services.attribution.benchmark_weights import benchmark_sector_weights_as_of

    if period_start is None:
        return benchmark_sector_weights_as_of(date.today(), allow_mock=allow_mock)
    return benchmark_sector_weights_as_of(period_start, allow_mock=allow_mock)


def calculate_brinson_attribution(
    positions: list[Position],
    base_currency: str,
    fx_resolver,
    allow_mock: bool,
    portfolio_sector_returns: Optional[dict[str, float]] = None,
    portfolio_sector_weights: Optional[dict[str, float]] = None,
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

    portfolio_weights = portfolio_sector_weights or _portfolio_sector_weights(positions, base_currency, fx_resolver)
    benchmark_weights = _benchmark_sector_weights(period_start, allow_mock=allow_mock)
    if not benchmark_weights:
        return (
            None,
            None,
            None,
            None,
            {},
            "Brinson attribution withheld: licensed or documented benchmark sector weights are unavailable.",
        )
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
        "Brinson-Fachler attribution uses beginning portfolio sector weights and value-weighted period "
        "portfolio sector returns versus documented static benchmark sector weights (demo/testing only) "
        "and ETF total returns."
    )
    if portfolio_sector_weights is not None:
        methodology += " Beginning weights are reconstructed from the transaction ledger."
    return (
        round(allocation * 100.0, 2),
        round(selection * 100.0, 2),
        round(interaction * 100.0, 2),
        round(total_active * 100.0, 2),
        by_sector,
        methodology,
    )


def _portfolio_sector_returns_from_reconstruction(
    positions: list[Position],
    reconstruction: dict,
) -> dict[str, float] | None:
    from collections import defaultdict

    asset_returns = reconstruction.get("asset_returns", {})
    if not asset_returns:
        return None
    sector_returns: dict[str, list[float]] = defaultdict(list)
    for position in positions:
        daily_returns = asset_returns.get(position.symbol)
        if not daily_returns:
            continue
        compounded = 1.0
        for daily_return in daily_returns:
            compounded *= 1.0 + daily_return
        sector_returns[position.sector or "Unknown"].append(compounded - 1.0)
    if not sector_returns:
        return None
    return {
        sector: sum(values) / len(values)
        for sector, values in sector_returns.items()
        if values
    }


def _position_pnl_key(position: Position) -> str:
    if position.con_id is not None:
        return f"{position.symbol.upper()}:{position.con_id}"
    return position.symbol.upper()


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
    from app.services.attribution.brinson_ledger import (
        beginning_sector_weights,
        sector_returns_from_ledger,
    )

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
                fx_resolver=fx_resolver,
            )
            if tax_lot_realized:
                tax_lot_total = round(sum(tax_lot_realized.values()), 2)
                tax_lot_status = "lot_matching_complete"

    security_selection_pnl: dict[str, float] = {}
    sector_allocation_pnl: dict[str, float] = defaultdict(float)
    asset_class_pnl: dict[str, float] = defaultdict(float)
    realized_val = 0.0
    unrealized_val = 0.0

    for pos in positions:
        rate = fx_resolver(pos.currency, base_currency)
        pnl = pos.unrealized_pnl * rate
        key = _position_pnl_key(pos)
        security_selection_pnl[key] = round(
            security_selection_pnl.get(key, 0.0) + pnl,
            2,
        )
        sector_name = pos.sector or "Unknown"
        sector_allocation_pnl[sector_name] += pnl

        aclass = "Single Stock"
        if pos.is_etf:
            aclass = "ETF"
        elif pos.asset_class == "OPT":
            aclass = "Options"
        elif "BND" in pos.asset_class or "BOND" in pos.asset_class:
            aclass = "Bonds"
        asset_class_pnl[aclass] += pnl

        realized_val += pos.realized_pnl * rate
        unrealized_val += pos.unrealized_pnl * rate

    sector_allocation_rounded = {key: round(value, 2) for key, value in sector_allocation_pnl.items()}
    asset_class_rounded = {key: round(value, 2) for key, value in asset_class_pnl.items()}

    benchmark_relative_alpha = None
    data_quality_benchmark = "withheld_modeled_alpha"
    allow_mock = "pytest" in sys.modules

    allocation_effect = None
    selection_effect = None
    interaction_effect = None
    total_active_return = None
    brinson_by_sector: dict[str, dict[str, float]] = {}
    methodology = (
        "Current unrealized P&L grouped by security, sector, and asset class in base currency. "
        "These fields are dollar P&L contributions, not return percentages. "
        "Brinson effects are withheld while attribution remains experimental."
    )

    brinson_status = "experimental_withheld"
    ledger_brinson_ready = False
    attribution_run_id: str | None = None

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

        from app.services.risk.history_reconstructor import reconstruct_portfolio_history

        recon = None
        portfolio_sector_returns = None
        portfolio_sector_weights = None
        period_start = None
        period_end = None
        ordered_history = sorted(history, key=lambda item: (item.date, item.timestamp))
        if ordered_history:
            period_start = date.fromisoformat(ordered_history[0].date)
            period_end = date.fromisoformat(ordered_history[-1].date)
        if account_id and period_start and period_end:
            coverage = load_ledger_coverage(account_id)
            if coverage and ledger_covers_period(coverage, period_start, period_end):
                ledger_transactions = get_transactions(account_id)
                portfolio_sector_weights = beginning_sector_weights(
                    ledger_transactions,
                    positions,
                    period_start,
                    base_currency,
                    fx_resolver,
                    allow_mock=allow_mock,
                )
                portfolio_sector_returns = sector_returns_from_ledger(
                    ledger_transactions,
                    positions,
                    period_start,
                    period_end,
                    allow_mock=allow_mock,
                    base_currency=base_currency,
                    fx_resolver=fx_resolver,
                )
                ledger_brinson_ready = bool(portfolio_sector_weights and portfolio_sector_returns)
        if "pytest" not in sys.modules:
            recon = reconstruct_portfolio_history(positions, summary, allow_mock=allow_mock)
            if portfolio_sector_returns is None and recon is not None:
                portfolio_sector_returns = _portfolio_sector_returns_from_reconstruction(positions, recon)

        # Brinson numerics emitted when ledger-backed sector returns are available.
        _alloc, _sel, _inter, _active, _by_sector, brinson_methodology = calculate_brinson_attribution(
            positions,
            base_currency,
            fx_resolver,
            allow_mock=allow_mock,
            portfolio_sector_returns=portfolio_sector_returns,
            portfolio_sector_weights=portfolio_sector_weights,
            period_start=period_start,
            period_end=period_end,
        )
        methodology = brinson_methodology
        if ledger_brinson_ready and _by_sector:
            allocation_effect = _alloc
            selection_effect = _sel
            interaction_effect = _inter
            total_active_return = _active
            brinson_by_sector = _by_sector
            brinson_status = "ledger_backed"
        elif _by_sector and allow_mock:
            brinson_status = "experimental_modeled"

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

    if ledger_brinson_ready and period_start and period_end and account_id:
        from app.services.analytics.calculation_run import create_calculation_run

        run = create_calculation_run(
            run_type="performance_attribution",
            account_id=account_id,
            exclusions=[] if brinson_by_sector else ["brinson_withheld"],
            coverage={
                "brinson_attribution": brinson_status,
                "cash_flow_adjustment": cash_flow_status,
            },
        )
        attribution_run_id = run.calculation_run_id

    return PerformanceAttribution(
        security_selection_pnl=security_selection_pnl,
        sector_allocation_pnl=sector_allocation_rounded,
        asset_class_pnl=asset_class_rounded,
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
            "brinson_attribution": brinson_status,
            "tax_lot_realized": tax_lot_status,
        },
        methodology=(
            "Current Unrealized P&L Decomposition. "
            + methodology
        ),
        calculation_run_id=attribution_run_id,
    )
