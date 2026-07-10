from __future__ import annotations

from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends

from app.api.deps import broker_not_configured_error, get_broker_adapter
from app.schemas.domain import AccountSummary, InvestmentPolicyStatement, InvestorProfile, Position, utc_now
from app.services.broker.base import BrokerAdapter
from app.services.broker.ibkr_readonly import get_exchange_rate
from app.services.data_quality.validation import validate_portfolio_snapshot
from app.services.risk.portfolio_risk import analyze_portfolio_risk

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


def _position_group_key(position: Position) -> tuple[str, ...]:
    if position.con_id is not None:
        return ("conid", str(position.con_id))
    return (
        position.symbol.upper(),
        position.asset_class.upper(),
        position.exchange.upper(),
        position.currency.upper(),
    )


def _get_consolidated_summary_and_positions(adapter: BrokerAdapter) -> tuple[AccountSummary, list[Position]]:
    accounts = adapter.get_accounts()
    if not accounts:
        raise broker_not_configured_error(Exception("No accounts found"))

    if len(accounts) == 1:
        account_id = accounts[0].id
        summary = adapter.get_account_summary(account_id).model_copy(update={"account_id": "all"})
        positions = [
            position.model_copy(update={"account_id": "all"})
            for position in adapter.get_positions(account_id)
        ]
        return summary, positions

    summaries: list[AccountSummary] = []
    all_positions: list[Position] = []
    failures: list[str] = []
    for account in accounts:
        try:
            summaries.append(adapter.get_account_summary(account.id))
            all_positions.extend(adapter.get_positions(account.id))
        except Exception as exc:
            failures.append(f"{account.id}: {exc}")

    # Accuracy-first behavior: never present a partial consolidated portfolio as
    # complete. The caller can request individual accounts to isolate the failure.
    if failures:
        raise broker_not_configured_error(
            RuntimeError("Incomplete consolidated snapshot: " + "; ".join(failures))
        )
    if not summaries:
        raise broker_not_configured_error(Exception("Failed to get summaries for all accounts"))

    base_currency = summaries[0].base_currency.upper()

    def converted(value: float, currency: str) -> float:
        return value * get_exchange_rate(currency, base_currency)

    consolidated_summary = AccountSummary(
        account_id="all",
        net_liquidation=round(sum(converted(item.net_liquidation, item.base_currency) for item in summaries), 2),
        cash=round(sum(converted(item.cash, item.base_currency) for item in summaries), 2),
        buying_power=round(sum(converted(item.buying_power, item.base_currency) for item in summaries), 2),
        margin_requirement=round(sum(converted(item.margin_requirement, item.base_currency) for item in summaries), 2),
        excess_liquidity=round(sum(converted(item.excess_liquidity, item.base_currency) for item in summaries), 2),
        total_unrealized_pnl=round(
            sum(converted(item.total_unrealized_pnl, item.base_currency) for item in summaries), 2
        ),
        total_realized_pnl=round(
            sum(converted(item.total_realized_pnl, item.base_currency) for item in summaries), 2
        ),
        base_currency=base_currency,
        # Use the oldest component timestamp so freshness checks cannot be hidden by
        # a newer account response.
        data_timestamp=min(item.data_timestamp for item in summaries),
    )

    grouped: dict[tuple[str, ...], list[Position]] = defaultdict(list)
    for position in all_positions:
        grouped[_position_group_key(position)].append(position)

    total_value = consolidated_summary.net_liquidation
    denominator = total_value if total_value != 0 else 1.0
    consolidated_positions: list[Position] = []

    for group in grouped.values():
        first = group[0]
        total_quantity = sum(position.quantity for position in group)
        total_market_value_base = 0.0
        total_unrealized_base = 0.0
        total_realized_base = 0.0
        absolute_quantity = 0.0
        weighted_cost_base = 0.0
        weighted_price_base = 0.0

        for position in group:
            rate = get_exchange_rate(position.currency, base_currency)
            quantity_weight = abs(position.quantity)
            total_market_value_base += position.market_value * rate
            total_unrealized_base += position.unrealized_pnl * rate
            total_realized_base += position.realized_pnl * rate
            absolute_quantity += quantity_weight
            weighted_cost_base += position.avg_cost * rate * quantity_weight
            weighted_price_base += position.market_price * rate * quantity_weight

        average_cost_base = weighted_cost_base / absolute_quantity if absolute_quantity else 0.0
        market_price_base = weighted_price_base / absolute_quantity if absolute_quantity else 0.0
        weight = total_market_value_base / denominator * 100.0

        consolidated_positions.append(
            Position(
                account_id="all",
                symbol=first.symbol,
                company_name=first.company_name,
                asset_class=first.asset_class,
                quantity=total_quantity,
                avg_cost=round(average_cost_base, 6),
                market_price=round(market_price_base, 6),
                market_value=round(total_market_value_base, 2),
                unrealized_pnl=round(total_unrealized_base, 2),
                realized_pnl=round(total_realized_base, 2),
                currency=base_currency,
                exchange=first.exchange,
                sector=first.sector,
                industry=first.industry,
                portfolio_weight=round(weight, 4),
                stock_type=first.stock_type,
                is_etf=first.is_etf,
                is_speculative=first.is_speculative,
                updated_at=min(position.updated_at for position in group),
                con_id=first.con_id,
                local_symbol=first.local_symbol,
                multiplier=first.multiplier,
                price_source=first.price_source,
            )
        )

    return consolidated_summary, consolidated_positions


def _resolve_account_data(
    adapter: BrokerAdapter,
    account_id: Optional[str],
) -> tuple[AccountSummary, list[Position]]:
    try:
        if not account_id or account_id == "all":
            accounts = adapter.get_accounts()
            if not accounts:
                raise RuntimeError("No accounts found")
            if len(accounts) == 1:
                resolved_id = accounts[0].id
                summary = adapter.get_account_summary(resolved_id)
                positions = adapter.get_positions(resolved_id)
                if account_id == "all":
                    summary = summary.model_copy(update={"account_id": "all"})
                    positions = [position.model_copy(update={"account_id": "all"}) for position in positions]
                return summary, positions
            return _get_consolidated_summary_and_positions(adapter)
        return adapter.get_account_summary(account_id), adapter.get_positions(account_id)
    except Exception as exc:
        raise broker_not_configured_error(exc) from exc


@router.get("/summary")
def summary(account_id: Optional[str] = None, adapter: BrokerAdapter = Depends(get_broker_adapter)):
    account_summary, account_positions = _resolve_account_data(adapter, account_id)
    data_quality = validate_portfolio_snapshot(account_summary, account_positions)
    risk_analysis = analyze_portfolio_risk(account_summary, account_positions)

    from app.services.suitability.engine import check_position_suitability, get_investor_profile

    active_id = account_id or account_summary.account_id or "default"
    profile = get_investor_profile(active_id)
    suitability_warnings: list[str] = []
    for position in account_positions:
        suitability_warnings.extend(check_position_suitability(profile, position))

    sorted_positions = sorted(account_positions, key=lambda position: abs(position.market_value), reverse=True)
    return {
        "summary": account_summary,
        "risk": risk_analysis,
        "positions": sorted_positions[:5],
        "suitability_warnings": suitability_warnings,
        "data_quality": data_quality,
    }


@router.get("/data-quality")
def data_quality(account_id: Optional[str] = None, adapter: BrokerAdapter = Depends(get_broker_adapter)):
    account_summary, account_positions = _resolve_account_data(adapter, account_id)
    return validate_portfolio_snapshot(account_summary, account_positions)


@router.get("/snapshots")
def snapshots(account_id: Optional[str] = None, adapter: BrokerAdapter = Depends(get_broker_adapter)):
    if account_id == "all":
        account_summary, _ = _resolve_account_data(adapter, "all")
        return [account_summary]
    if not account_id:
        return [adapter.get_account_summary(account.id) for account in adapter.get_accounts()]
    account_summary, _ = _resolve_account_data(adapter, account_id)
    return [account_summary]


@router.get("/positions")
def positions(account_id: Optional[str] = None, adapter: BrokerAdapter = Depends(get_broker_adapter)):
    _, account_positions = _resolve_account_data(adapter, account_id)
    return account_positions


@router.get("/allocation")
def allocation(account_id: Optional[str] = None, adapter: BrokerAdapter = Depends(get_broker_adapter)):
    account_summary, account_positions = _resolve_account_data(adapter, account_id)
    return {
        "by_sector": _group_percent(account_positions, account_summary.base_currency, "sector"),
        "by_currency": _group_percent(account_positions, account_summary.base_currency, "currency"),
        "by_asset_class": _group_percent(account_positions, account_summary.base_currency, "asset_class"),
        "methodology": "Gross absolute market-value allocation after base-currency conversion.",
    }


@router.get("/performance")
def performance(account_id: Optional[str] = None, adapter: BrokerAdapter = Depends(get_broker_adapter)):
    account_summary, _ = _resolve_account_data(adapter, account_id)

    from app.services.portfolio.performance_returns import calculate_performance_returns
    from app.services.portfolio.pnl_tracker import get_pnl_history

    active_id = account_id or account_summary.account_id or "default"
    history = get_pnl_history(None if active_id == "all" else active_id)
    history = sorted(history, key=lambda item: (item.date, item.timestamp))
    latest = history[-1] if history else None
    returns = calculate_performance_returns(
        active_id if active_id != "all" else "default",
        history,
        account_summary.base_currency,
        get_exchange_rate,
    )

    return {
        "total_unrealized_pnl": account_summary.total_unrealized_pnl,
        "total_realized_pnl": account_summary.total_realized_pnl,
        "daily_return": returns.daily_returns[-1]["investment_return_percent"] if returns.daily_returns else None,
        "time_weighted_return": returns.time_weighted_return,
        "time_weighted_return_annualized": returns.time_weighted_return_annualized,
        "xirr": returns.xirr,
        "benchmark_comparison": returns.benchmark_comparison,
        "account_value_change": latest.daily_pnl if latest else None,
        "account_value_change_percent": latest.daily_pnl_percent if latest else None,
        "data_quality": returns.data_quality,
        "methodology": returns.methodology,
    }


@router.get("/score-calibration")
def score_calibration(model_name: str = "universal"):
    from app.services.scoring.calibration import run_score_calibration

    # Demo calibration uses reproducible score/return pairs until live walk-forward history is stored.
    observations = [
        {"symbol": "MSFT", "score": 82.0, "forward_return": 0.12},
        {"symbol": "META", "score": 78.0, "forward_return": 0.09},
        {"symbol": "IONQ", "score": 48.0, "forward_return": -0.08},
        {"symbol": "QQQ", "score": 74.0, "forward_return": 0.07},
        {"symbol": "SOFI", "score": 55.0, "forward_return": 0.01},
        {"symbol": "NKE", "score": 42.0, "forward_return": -0.04},
        {"symbol": "CRM", "score": 69.0, "forward_return": 0.05},
        {"symbol": "GOOGL", "score": 76.0, "forward_return": 0.08},
        {"symbol": "LAES", "score": 35.0, "forward_return": -0.15},
        {"symbol": "SPY", "score": 71.0, "forward_return": 0.06},
        {"symbol": "CELH", "score": 58.0, "forward_return": 0.02},
        {"symbol": "INFQ", "score": 31.0, "forward_return": -0.12},
        {"symbol": "SOXX", "score": 73.0, "forward_return": 0.10},
        {"symbol": "AAPL", "score": 80.0, "forward_return": 0.11},
        {"symbol": "NVDA", "score": 84.0, "forward_return": 0.18},
        {"symbol": "TSLA", "score": 52.0, "forward_return": -0.02},
        {"symbol": "AMZN", "score": 77.0, "forward_return": 0.09},
        {"symbol": "MSFT", "score": 79.0, "forward_return": 0.06},
        {"symbol": "META", "score": 75.0, "forward_return": 0.04},
        {"symbol": "QQQ", "score": 72.0, "forward_return": 0.05},
    ]
    return run_score_calibration(observations, model_name=model_name)


@router.get("/risk")
def risk(account_id: Optional[str] = None, adapter: BrokerAdapter = Depends(get_broker_adapter)):
    account_summary, account_positions = _resolve_account_data(adapter, account_id)
    return analyze_portfolio_risk(account_summary, account_positions)


def _group_percent(positions: list[Position], base_currency: str, field: str) -> dict[str, float]:
    grouped: dict[str, float] = defaultdict(float)
    for position in positions:
        rate = get_exchange_rate(position.currency, base_currency)
        grouped[str(getattr(position, field) or "Unknown")] += abs(position.market_value * rate)
    total = sum(grouped.values())
    if total <= 0:
        return {key: 0.0 for key in sorted(grouped)}
    return {key: round(value / total * 100.0, 2) for key, value in sorted(grouped.items())}


@router.get("/profile", response_model=InvestorProfile)
def get_profile(account_id: Optional[str] = "default"):
    from app.services.suitability.engine import get_investor_profile

    return get_investor_profile(account_id)


@router.post("/profile")
def update_profile(profile: InvestorProfile, account_id: Optional[str] = "default"):
    from app.services.suitability.engine import save_investor_profile

    save_investor_profile(profile, account_id)
    return {"status": "success", "message": "Investor profile updated successfully"}


@router.get("/policy", response_model=InvestmentPolicyStatement)
def get_policy(account_id: Optional[str] = "default"):
    from app.services.policy.engine import get_portfolio_policy

    return get_portfolio_policy(account_id)


@router.post("/policy")
def update_policy(policy: InvestmentPolicyStatement, account_id: Optional[str] = "default"):
    from app.services.policy.engine import save_portfolio_policy

    save_portfolio_policy(policy, account_id)
    return {"status": "success", "message": "Investment Policy Statement updated successfully"}


@router.get("/advanced-risk")
def get_advanced_portfolio_risk(
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
):
    from app.services.portfolio.pnl_tracker import get_pnl_history
    from app.services.risk.advanced_risk import calculate_advanced_risk_metrics

    account_summary, account_positions = _resolve_account_data(adapter, account_id)
    active_id = account_id or account_summary.account_id or "default"
    history = get_pnl_history(None if active_id == "all" else active_id)
    return calculate_advanced_risk_metrics(account_positions, account_summary, history)


@router.get("/attribution")
def get_portfolio_attribution(
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
):
    from app.services.attribution.engine import calculate_performance_attribution
    from app.services.portfolio.pnl_tracker import get_pnl_history

    account_summary, account_positions = _resolve_account_data(adapter, account_id)
    active_id = account_id or account_summary.account_id or "default"
    history = get_pnl_history(None if active_id == "all" else active_id)
    return calculate_performance_attribution(
        account_positions,
        history,
        base_currency=account_summary.base_currency,
        fx_resolver=get_exchange_rate,
        account_id=None if active_id == "all" else active_id,
    )


@router.get("/tax-lots")
def tax_lot_attribution(account_id: Optional[str] = None, adapter: BrokerAdapter = Depends(get_broker_adapter)):
    from app.services.portfolio.tax_lots import build_tax_lot_attribution
    from app.services.portfolio.transaction_store import get_transactions, sync_transactions

    account_summary, _ = _resolve_account_data(adapter, account_id)
    active_id = account_id or account_summary.account_id or "default"
    if active_id == "all":
        active_id = adapter.get_accounts()[0].id
    transactions = get_transactions(active_id)
    if not transactions:
        sync_transactions(adapter, active_id)
        transactions = get_transactions(active_id)
    return build_tax_lot_attribution(active_id, transactions)


@router.get("/fundamentals/{symbol}/point-in-time")
def point_in_time_fundamentals(symbol: str, as_of: Optional[str] = None):
    from datetime import date as date_type

    from app.services.fundamentals.mock_provider import MockFundamentalProvider
    from app.services.fundamentals.snapshot_store import get_point_in_time_fundamentals, seed_walk_forward_demo_records

    as_of_date = date_type.fromisoformat(as_of) if as_of else date_type.today()
    snapshot = get_point_in_time_fundamentals(symbol, as_of_date)
    if snapshot is None:
        provider = MockFundamentalProvider(allow_mock=True)
        base = provider.get_fundamentals(symbol)
        seed_walk_forward_demo_records(symbol, base)
        snapshot = get_point_in_time_fundamentals(symbol, as_of_date)
    if snapshot is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"No point-in-time fundamentals for {symbol.upper()} on {as_of_date}")
    return {
        "symbol": symbol.upper(),
        "as_of_date": as_of_date.isoformat(),
        "snapshot": snapshot,
        "point_in_time": True,
    }
