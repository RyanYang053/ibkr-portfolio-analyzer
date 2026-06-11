from fastapi import APIRouter, Depends

from app.api.deps import broker_not_configured_error, get_broker_adapter
from app.services.broker.base import BrokerAdapter
from app.services.risk.portfolio_risk import analyze_portfolio_risk


router = APIRouter(prefix="/portfolio", tags=["portfolio"])


from typing import Optional
from app.schemas.domain import AccountSummary, Position, utc_now
from app.services.broker.ibkr_readonly import get_exchange_rate

def _get_consolidated_summary_and_positions(adapter: BrokerAdapter) -> tuple[AccountSummary, list[Position]]:
    accounts = adapter.get_accounts()
    if not accounts:
        raise broker_not_configured_error(Exception("No accounts found"))
    
    if len(accounts) == 1:
        acct_id = accounts[0].id
        summary = adapter.get_account_summary(acct_id)
        positions = adapter.get_positions(acct_id)
        consolidated_summary = summary.model_copy(update={"account_id": "all"})
        consolidated_positions = [p.model_copy(update={"account_id": "all"}) for p in positions]
        return consolidated_summary, consolidated_positions
        
    summaries = []
    all_positions = []
    for acct in accounts:
        try:
            summaries.append(adapter.get_account_summary(acct.id))
            all_positions.extend(adapter.get_positions(acct.id))
        except Exception:
            pass
            
    if not summaries:
        raise broker_not_configured_error(Exception("Failed to get summaries for any account"))
        
    base_currency = summaries[0].base_currency
    
    net_liq = 0.0
    cash = 0.0
    buying_power = 0.0
    margin_req = 0.0
    excess_liq = 0.0
    unrealized = 0.0
    realized = 0.0
    
    for s in summaries:
        rate = get_exchange_rate(s.base_currency, base_currency)
        net_liq += s.net_liquidation * rate
        cash += s.cash * rate
        buying_power += s.buying_power * rate
        margin_req += s.margin_requirement * rate
        excess_liq += s.excess_liquidity * rate
        unrealized += s.total_unrealized_pnl * rate
        realized += s.total_realized_pnl * rate
        
    consolidated_summary = AccountSummary(
        account_id="all",
        net_liquidation=round(net_liq, 2),
        cash=round(cash, 2),
        buying_power=round(buying_power, 2),
        margin_requirement=round(margin_req, 2),
        excess_liquidity=round(excess_liq, 2),
        total_unrealized_pnl=round(unrealized, 2),
        total_realized_pnl=round(realized, 2),
        base_currency=base_currency,
        data_timestamp=utc_now()
    )
    
    # Consolidate positions
    from collections import defaultdict
    grouped = defaultdict(list)
    for p in all_positions:
        grouped[p.symbol].append(p)
        
    consolidated_positions = []
    total_val = max(net_liq, 1.0)
    
    for symbol, group in grouped.items():
        first = group[0]
        total_qty = sum(p.quantity for p in group)
        total_mv = sum(p.market_value for p in group)
        total_unrealized = sum(p.unrealized_pnl for p in group)
        total_realized = sum(p.realized_pnl for p in group)
        
        if total_qty > 0:
            avg_cost = sum(p.avg_cost * p.quantity for p in group) / total_qty
        else:
            avg_cost = 0.0
            
        rate = get_exchange_rate(first.currency, base_currency)
        market_value_base = total_mv * rate
        weight = round(market_value_base / total_val * 100, 2)
        
        consolidated_positions.append(Position(
            account_id="all",
            symbol=symbol,
            company_name=first.company_name,
            asset_class=first.asset_class,
            quantity=total_qty,
            avg_cost=round(avg_cost, 2),
            market_price=first.market_price,
            market_value=round(total_mv, 2),
            unrealized_pnl=round(total_unrealized, 2),
            realized_pnl=round(total_realized, 2),
            currency=first.currency,
            exchange=first.exchange,
            sector=first.sector,
            industry=first.industry,
            portfolio_weight=weight,
            stock_type=first.stock_type,
            is_etf=first.is_etf,
            is_speculative=first.is_speculative,
            updated_at=first.updated_at
        ))
        
    return consolidated_summary, consolidated_positions


def _resolve_account_data(adapter: BrokerAdapter, account_id: Optional[str]) -> tuple[AccountSummary, list[Position]]:
    try:
        if not account_id or account_id == "all":
            accounts = adapter.get_accounts()
            if not accounts:
                raise Exception("No accounts found")
            if len(accounts) == 1:
                acct_id = accounts[0].id
                summary = adapter.get_account_summary(acct_id)
                positions = adapter.get_positions(acct_id)
                if account_id == "all":
                    summary = summary.model_copy(update={"account_id": "all"})
                    positions = [p.model_copy(update={"account_id": "all"}) for p in positions]
                return summary, positions
            if account_id == "all":
                return _get_consolidated_summary_and_positions(adapter)
            # Default to first account if none specified
            acct_id = accounts[0].id
            return adapter.get_account_summary(acct_id), adapter.get_positions(acct_id)
        else:
            return adapter.get_account_summary(account_id), adapter.get_positions(account_id)
    except Exception as exc:
        raise broker_not_configured_error(exc) from exc


@router.get("/summary")
def summary(account_id: Optional[str] = None, adapter: BrokerAdapter = Depends(get_broker_adapter)):
    account_summary, positions = _resolve_account_data(adapter, account_id)
    risk_analysis = analyze_portfolio_risk(account_summary, positions)
    sorted_positions = sorted(positions, key=lambda p: p.market_value, reverse=True)
    return {"summary": account_summary, "risk": risk_analysis, "positions": sorted_positions[:5]}


@router.get("/snapshots")
def snapshots(account_id: Optional[str] = None, adapter: BrokerAdapter = Depends(get_broker_adapter)):
    if account_id == "all":
        summary, _ = _resolve_account_data(adapter, "all")
        return [summary]
    if not account_id:
        accounts = adapter.get_accounts()
        return [adapter.get_account_summary(a.id) for a in accounts]
    summary, _ = _resolve_account_data(adapter, account_id)
    return [summary]


@router.get("/positions")
def positions(account_id: Optional[str] = None, adapter: BrokerAdapter = Depends(get_broker_adapter)):
    _, positions = _resolve_account_data(adapter, account_id)
    return positions


@router.get("/allocation")
def allocation(account_id: Optional[str] = None, adapter: BrokerAdapter = Depends(get_broker_adapter)):
    _, positions = _resolve_account_data(adapter, account_id)
    total = sum(position.market_value for position in positions)
    if total <= 0:
        total = 1.0
    return {
        "by_sector": _group_percent(positions, total, "sector"),
        "by_currency": _group_percent(positions, total, "currency"),
        "by_asset_class": _group_percent(positions, total, "asset_class"),
    }


@router.get("/performance")
def performance(account_id: Optional[str] = None, adapter: BrokerAdapter = Depends(get_broker_adapter)):
    summary_data, _ = _resolve_account_data(adapter, account_id)
    return {
        "total_unrealized_pnl": summary_data.total_unrealized_pnl,
        "total_realized_pnl": summary_data.total_realized_pnl,
        "daily_return": 0.003,
        "benchmark_comparison": {"SPY": 0.0018, "QQQ": 0.0026},
    }


@router.get("/risk")
def risk(account_id: Optional[str] = None, adapter: BrokerAdapter = Depends(get_broker_adapter)):
    summary_data, positions = _resolve_account_data(adapter, account_id)
    return analyze_portfolio_risk(summary_data, positions)


def _group_percent(positions, total: float, field: str) -> dict[str, float]:
    grouped: dict[str, float] = {}
    for position in positions:
        grouped[getattr(position, field)] = grouped.get(getattr(position, field), 0) + position.market_value
    return {key: round(value / total * 100, 2) for key, value in grouped.items()}
