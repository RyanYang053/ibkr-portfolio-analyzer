from __future__ import annotations

from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth_deps import Principal, get_current_principal, require_scope
from app.api.account_deps import ensure_account_access, resolve_authorized_account_id, resolve_authorized_account_ids
from app.api.deps import broker_not_configured_error, get_broker_adapter
from app.schemas.domain import AccountSummary, InvestmentPolicyStatement, InvestorProfile, Position, utc_now
from app.services.broker.base import BrokerAdapter
from app.services.broker.ibkr_readonly import get_exchange_rate
from app.services.data_quality.validation import (
    prepare_professional_response,
    require_analytics_safe,
    validate_and_gate_snapshot,
    validate_portfolio_snapshot,
)
from app.services.risk.portfolio_risk import analyze_portfolio_risk
from app.services.tenant_scope import tenant_user_id

router = APIRouter(
    prefix="/portfolio",
    tags=["portfolio"],
    dependencies=[Depends(get_current_principal)],
)


def _position_group_key(position: Position) -> tuple[str, ...]:
  side = "long" if position.quantity >= 0 else "short"
  if position.con_id is not None:
    return ("conid", str(position.con_id), side)
  return (
    position.symbol.upper(),
    position.asset_class.upper(),
    position.exchange.upper(),
    position.currency.upper(),
    side,
  )


def _get_consolidated_summary_and_positions(
    adapter: BrokerAdapter,
    account_ids: list[str],
) -> tuple[AccountSummary, list[Position]]:
    if not account_ids:
        raise broker_not_configured_error(Exception("No accounts found"))

    if len(account_ids) == 1:
        account_id = account_ids[0]
        summary = adapter.get_account_summary(account_id).model_copy(update={"account_id": "all"})
        positions = [
            position.model_copy(update={"account_id": "all"})
            for position in adapter.get_positions(account_id)
        ]
        return summary, positions

    summaries: list[AccountSummary] = []
    all_positions: list[Position] = []
    failures: list[str] = []
    for account_id in account_ids:
        try:
            summaries.append(adapter.get_account_summary(account_id))
            all_positions.extend(adapter.get_positions(account_id))
        except Exception as exc:
            failures.append(f"{account_id}: {exc}")

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
    principal: Principal,
) -> tuple[AccountSummary, list[Position]]:
    try:
        allowed_ids = resolve_authorized_account_ids(adapter, principal, account_id)
        if len(allowed_ids) == 1:
            resolved_id = allowed_ids[0]
            summary = adapter.get_account_summary(resolved_id)
            positions = adapter.get_positions(resolved_id)
            if account_id == "all":
                summary = summary.model_copy(update={"account_id": "all"})
                positions = [position.model_copy(update={"account_id": "all"}) for position in positions]
            return summary, positions
        return _get_consolidated_summary_and_positions(adapter, allowed_ids)
    except HTTPException:
        raise
    except Exception as exc:
        raise broker_not_configured_error(exc) from exc


@router.get("/summary")
def summary(
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    account_summary, account_positions = _resolve_account_data(adapter, account_id, principal)
    data_quality = validate_portfolio_snapshot(account_summary, account_positions)
    require_analytics_safe(data_quality)
    risk_analysis = analyze_portfolio_risk(account_summary, account_positions)

    from app.services.suitability.engine import check_position_suitability, get_investor_profile

    active_id = resolve_authorized_account_id(account_id, adapter, principal)
    profile = get_investor_profile(active_id, user_id=tenant_user_id(principal))
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
def data_quality(
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    account_summary, account_positions = _resolve_account_data(adapter, account_id, principal)
    return validate_portfolio_snapshot(account_summary, account_positions)


@router.get("/snapshots")
def snapshots(
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    if account_id == "all":
        account_summary, account_positions = _resolve_account_data(adapter, "all", principal)
        require_analytics_safe(validate_portfolio_snapshot(account_summary, account_positions))
        return [account_summary]
    resolved_ids = resolve_authorized_account_ids(adapter, principal, account_id)
    resolved_id = resolved_ids[0]
    summary = adapter.get_account_summary(resolved_id)
    positions = adapter.get_positions(resolved_id)
    require_analytics_safe(validate_portfolio_snapshot(summary, positions))
    return [summary]


@router.get("/positions", response_model=list[Position])
def positions(
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    account_summary, account_positions = _resolve_account_data(adapter, account_id, principal)
    require_analytics_safe(validate_portfolio_snapshot(account_summary, account_positions))
    return account_positions


@router.get("/allocation")
def allocation(
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    account_summary, account_positions = _resolve_account_data(adapter, account_id, principal)
    validation = validate_and_gate_snapshot(account_summary, account_positions)
    result = {
        "by_sector": _group_percent(account_positions, account_summary.base_currency, "sector"),
        "by_currency": _group_percent(account_positions, account_summary.base_currency, "currency"),
        "by_asset_class": _group_percent(account_positions, account_summary.base_currency, "asset_class"),
        "methodology": "Gross absolute market-value allocation after base-currency conversion.",
    }
    return prepare_professional_response(result, account_summary, account_positions, validation)


@router.get("/performance")
def performance(
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    account_summary, account_positions = _resolve_account_data(adapter, account_id, principal)
    validation = validate_and_gate_snapshot(account_summary, account_positions)

    from app.core.config import settings
    from app.services.market_data.fx_store import make_transaction_fx_resolver
    from app.services.portfolio.account_scope import require_single_account_id
    from app.services.portfolio.performance_returns import calculate_performance_returns
    from app.services.portfolio.pnl_tracker import get_pnl_history

    active_id = require_single_account_id(account_id, account_summary.account_id, adapter)
    history = get_pnl_history(active_id)
    history = sorted(history, key=lambda item: (item.date, item.timestamp))
    latest = history[-1] if history else None
    allow_mock = settings.broker_mode == "mock_ibkr_readonly"
    returns = calculate_performance_returns(
        active_id,
        history,
        account_summary.base_currency,
        make_transaction_fx_resolver(),
        allow_mock=allow_mock,
    )

    return prepare_professional_response(
        {
            "total_unrealized_pnl": account_summary.total_unrealized_pnl,
            "total_realized_pnl": account_summary.total_realized_pnl,
            "daily_return": returns.daily_returns[-1]["investment_return_percent"] if returns.daily_returns else None,
            "time_weighted_return": returns.time_weighted_return,
            "time_weighted_return_annualized": returns.time_weighted_return_annualized,
            "modified_dietz_return": returns.modified_dietz_return,
            "modified_dietz_return_annualized": returns.modified_dietz_return_annualized,
            "return_methodology": returns.return_methodology,
            "xirr": returns.xirr,
            "calculation_run_id": returns.calculation_run_id,
            "benchmark_comparison": returns.benchmark_comparison,
            "account_value_change": latest.daily_pnl if latest else None,
            "account_value_change_percent": latest.daily_pnl_percent if latest else None,
            "data_quality": returns.data_quality,
            "methodology": returns.methodology,
        },
        account_summary,
        account_positions,
        validation,
    )


@router.get("/pnl-decomposition")
def pnl_decomposition(
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    from app.services.market_data.fx_store import make_transaction_fx_resolver
    from app.services.portfolio.account_scope import require_single_account_id
    from app.services.portfolio.pnl_decomposition import calculate_pnl_decomposition
    from app.services.portfolio.pnl_tracker import get_pnl_history

    account_summary, account_positions = _resolve_account_data(adapter, account_id, principal)
    validation = validate_and_gate_snapshot(account_summary, account_positions)
    active_id = require_single_account_id(account_id, account_summary.account_id, adapter)
    history = get_pnl_history(active_id)
    result = calculate_pnl_decomposition(
        active_id,
        history,
        account_positions,
        account_summary.base_currency,
        make_transaction_fx_resolver(),
    )
    return prepare_professional_response(result.model_dump(), account_summary, account_positions, validation)


@router.get("/reconciliation")
def reconciliation(
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    from app.services.market_data.fx_store import make_transaction_fx_resolver
    from app.services.portfolio.account_scope import require_single_account_id
    from app.services.portfolio.pnl_decomposition import calculate_pnl_decomposition
    from app.services.portfolio.pnl_tracker import get_pnl_history

    account_summary, account_positions = _resolve_account_data(adapter, account_id, principal)
    validation = validate_and_gate_snapshot(account_summary, account_positions)
    active_id = require_single_account_id(account_id, account_summary.account_id, adapter)
    history = get_pnl_history(active_id)
    decomposition = calculate_pnl_decomposition(
        active_id,
        history,
        account_positions,
        account_summary.base_currency,
        make_transaction_fx_resolver(),
    )
    payload = {
        "account_id": active_id,
        "reconciliation_status": decomposition.reconciliation_status,
        "reconciliation_gap": decomposition.reconciliation_gap,
        "account_value_change": decomposition.account_value_change,
        "explained_components": {
            "price_effect_total": decomposition.price_effect_total,
            "dividend_income_total": decomposition.dividend_income_total,
            "fee_expense_total": decomposition.fee_expense_total,
            "interest_income_total": decomposition.interest_income_total,
            "corporate_action_total": decomposition.corporate_action_total,
            "external_cash_flow_total": decomposition.external_cash_flow_total,
            "residual_total": decomposition.residual_total,
        },
        "calculation_run": decomposition.calculation_run,
        "methodology": decomposition.methodology,
    }
    return prepare_professional_response(payload, account_summary, account_positions, validation)


@router.get("/research-context")
def research_context(
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    from app.core.config import settings
    from app.schemas.domain import DataQualityContext, SourceRecord
    from app.services.ai.portfolio_research import build_portfolio_research_context
    from app.services.attribution.engine import calculate_performance_attribution
    from app.services.market_data.fx_store import make_transaction_fx_resolver
    from app.services.policy.engine import get_portfolio_policy
    from app.services.portfolio.account_scope import require_single_account_id
    from app.services.portfolio.performance_returns import calculate_performance_returns
    from app.services.portfolio.pnl_tracker import get_pnl_history
    from app.services.risk.advanced_risk import calculate_advanced_risk_metrics
    from app.services.suitability.engine import get_investor_profile

    account_summary, account_positions = _resolve_account_data(adapter, account_id, principal)
    validation = validate_and_gate_snapshot(account_summary, account_positions)
    active_id = require_single_account_id(account_id, account_summary.account_id, adapter)
    history = get_pnl_history(active_id)
    allow_mock = settings.broker_mode == "mock_ibkr_readonly"
    performance = calculate_performance_returns(
        active_id,
        history,
        account_summary.base_currency,
        make_transaction_fx_resolver(),
        allow_mock=allow_mock,
    )
    attribution = calculate_performance_attribution(
        account_positions,
        history,
        base_currency=account_summary.base_currency,
        fx_resolver=make_transaction_fx_resolver(),
    )
    risk = calculate_advanced_risk_metrics(account_positions, account_summary, history)
    policy = get_portfolio_policy(active_id, user_id=tenant_user_id(principal))
    profile = get_investor_profile(active_id, user_id=tenant_user_id(principal))
    run_ids = [
        value
        for value in [performance.calculation_run_id, risk.calculation_run_id]
        if value
    ]
    context = build_portfolio_research_context(
        user_id=tenant_user_id(principal),
        account_id=active_id,
        reporting_currency=account_summary.base_currency,
        performance=performance.model_dump(),
        attribution=attribution.model_dump(),
        risk=risk.model_dump(),
        exposures=_group_percent(account_positions, account_summary.base_currency, "sector"),
        holdings=[position.model_dump() for position in account_positions],
        events=_portfolio_research_events(account_positions),
        policy=policy.model_dump(),
        suitability=profile.model_dump(),
        data_quality=DataQualityContext(
            ledger_status=performance.data_quality.get("ledger_status", "unknown"),
            performance_status=performance.return_methodology,
            risk_status=risk.data_quality.get("historical_metrics", "unknown"),
            attribution_status=attribution.data_quality.get("brinson_attribution", "unknown"),
        ),
        sources=[SourceRecord(source_id="broker_snapshot", source_type="broker", label="IBKR read-only snapshot")],
        calculation_run_ids=run_ids,
    )
    return prepare_professional_response(context.model_dump(), account_summary, account_positions, validation)


@router.get("/score-calibration")
def score_calibration(model_name: str = "universal"):
    from app.core.config import settings
    from app.services.scoring.calibration import (
        demo_calibration_observations,
        load_calibration_observations,
        run_score_calibration,
    )
    from app.services.scoring.calibration_ingestion import materialize_calibration_observations

    allow_mock = settings.broker_mode == "mock_ibkr_readonly"
    materialize_calibration_observations(model_name, allow_mock=allow_mock)
    if allow_mock:
        observations = demo_calibration_observations()
    else:
        observations = load_calibration_observations(model_name)
    return run_score_calibration(observations, model_name=model_name)


@router.get("/risk")
def risk(
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    account_summary, account_positions = _resolve_account_data(adapter, account_id, principal)
    validation = validate_portfolio_snapshot(account_summary, account_positions)
    require_analytics_safe(validation)
    return analyze_portfolio_risk(account_summary, account_positions)


def _portfolio_research_events(positions: list[Position]) -> list[dict]:
    from app.core.config import settings
    from app.services.market_data.mock_provider import MockMarketDataProvider
    from app.services.research.event_taxonomy import classify_news_event

    allow_mock = settings.broker_mode == "mock_ibkr_readonly"
    provider = MockMarketDataProvider(allow_mock=allow_mock)
    events: list[dict] = []
    for position in positions[:5]:
        try:
            for item in provider.get_recent_news(position.symbol)[:2]:
                headline = str(item.get("title") or item.get("headline") or "")
                if not headline:
                    continue
                event = classify_news_event(headline, str(item.get("summary", "")))
                event.symbol = position.symbol
                events.append(event.model_dump())
        except Exception:
            continue
    return events


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
def get_profile(
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    active_id = resolve_authorized_account_id(account_id, adapter, principal)
    from app.services.suitability.engine import get_investor_profile

    return get_investor_profile(active_id, user_id=tenant_user_id(principal))


@router.post("/profile", dependencies=[Depends(require_scope("portfolio:write"))])
def update_profile(
    profile: InvestorProfile,
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    active_id = resolve_authorized_account_id(account_id, adapter, principal)
    from app.services.suitability.engine import save_investor_profile

    save_investor_profile(profile, active_id, user_id=tenant_user_id(principal))
    return {"status": "success", "message": "Investor profile updated successfully"}


@router.get("/policy", response_model=InvestmentPolicyStatement)
def get_policy(
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    active_id = resolve_authorized_account_id(account_id, adapter, principal)
    from app.services.policy.engine import get_portfolio_policy

    return get_portfolio_policy(active_id, user_id=tenant_user_id(principal))


@router.post("/policy", dependencies=[Depends(require_scope("portfolio:write"))])
def update_policy(
    policy: InvestmentPolicyStatement,
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    active_id = resolve_authorized_account_id(account_id, adapter, principal)
    from app.services.policy.engine import save_portfolio_policy

    save_portfolio_policy(policy, active_id, user_id=tenant_user_id(principal))
    return {"status": "success", "message": "Investment Policy Statement updated successfully"}


@router.get("/advanced-risk")
def get_advanced_portfolio_risk(
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    from app.services.portfolio.account_scope import require_single_account_id
    from app.services.portfolio.pnl_tracker import get_pnl_history
    from app.services.risk.advanced_risk import calculate_advanced_risk_metrics

    account_summary, account_positions = _resolve_account_data(adapter, account_id, principal)
    validation = validate_and_gate_snapshot(account_summary, account_positions)
    active_id = require_single_account_id(account_id, account_summary.account_id, adapter)
    history = get_pnl_history(active_id)
    result = calculate_advanced_risk_metrics(account_positions, account_summary, history)
    return prepare_professional_response(result, account_summary, account_positions, validation)


@router.get("/attribution")
def get_portfolio_attribution(
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    from app.services.attribution.engine import calculate_performance_attribution
    from app.services.portfolio.pnl_tracker import get_pnl_history

    from app.services.market_data.fx_store import make_transaction_fx_resolver
    from app.services.portfolio.account_scope import require_single_account_id

    account_summary, account_positions = _resolve_account_data(adapter, account_id, principal)
    validation = validate_and_gate_snapshot(account_summary, account_positions)
    active_id = require_single_account_id(account_id, account_summary.account_id, adapter)
    history = get_pnl_history(active_id)
    result = calculate_performance_attribution(
        account_positions,
        history,
        base_currency=account_summary.base_currency,
        fx_resolver=make_transaction_fx_resolver(),
        account_id=active_id,
    )
    return prepare_professional_response(result, account_summary, account_positions, validation)


@router.get("/decision-journal")
def decision_journal(
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    from app.services.governance.decision_journal import list_decision_journal_entries
    from app.services.portfolio.account_scope import require_single_account_id

    account_summary, _ = _resolve_account_data(adapter, account_id, principal)
    active_id = require_single_account_id(account_id, account_summary.account_id, adapter)
    entries = list_decision_journal_entries(tenant_user_id(principal), active_id)
    return {"account_id": active_id, "entries": entries}


@router.get("/ledger-coverage")
def ledger_coverage(
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    from app.services.portfolio.account_scope import require_single_account_id
    from app.services.portfolio.transaction_store import get_ledger_coverage

    account_summary, account_positions = _resolve_account_data(adapter, account_id, principal)
    require_analytics_safe(validate_portfolio_snapshot(account_summary, account_positions))
    active_id = require_single_account_id(account_id, account_summary.account_id, adapter)
    coverage = get_ledger_coverage(active_id)
    if coverage is None:
        return {
            "account_id": active_id,
            "status": "missing",
            "has_external_cash_flows": False,
            "execution_only": False,
        }
    return coverage


@router.get("/tax-lots")
def tax_lot_attribution(
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    from datetime import date as date_type

    from app.services.market_data.fx_store import make_transaction_fx_resolver
    from app.services.portfolio.tax_lots import build_tax_lot_attribution
    from app.services.portfolio.pnl_tracker import get_pnl_history
    from app.services.portfolio.transaction_store import get_transactions, sync_transactions
    from app.services.portfolio.account_scope import require_single_account_id
    from app.services.suitability.engine import get_investor_profile

    account_summary, account_positions = _resolve_account_data(adapter, account_id, principal)
    validation = validate_and_gate_snapshot(account_summary, account_positions)
    active_id = require_single_account_id(account_id, account_summary.account_id, adapter)
    transactions = get_transactions(active_id)
    if not transactions:
        sync_transactions(adapter, active_id)
        transactions = get_transactions(active_id)

    history = get_pnl_history(active_id)
    ordered = sorted(history, key=lambda item: (item.date, item.timestamp))
    period_start = date_type.fromisoformat(ordered[0].date) if ordered else None
    period_end = date_type.fromisoformat(ordered[-1].date) if ordered else None
    profile = get_investor_profile(active_id, user_id=tenant_user_id(principal))
    jurisdiction = "US" if profile.tax_residency == "US" else "CA" if profile.tax_residency == "Canada" else "OTHER"

    result = build_tax_lot_attribution(
        active_id,
        transactions,
        reporting_currency=account_summary.base_currency,
        period_start=period_start,
        period_end=period_end,
        tax_labeling_jurisdiction=jurisdiction,
        fx_resolver=make_transaction_fx_resolver(),
    )
    return prepare_professional_response(result, account_summary, account_positions, validation)


@router.get("/rebalance-proposal")
def rebalance_proposal(
    account_id: Optional[str] = None,
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    from app.services.policy.engine import get_portfolio_policy
    from app.services.portfolio_construction.engine import generate_rebalance_proposal
    from app.services.portfolio.account_scope import require_single_account_id
    from app.services.suitability.engine import get_investor_profile

    account_summary, account_positions = _resolve_account_data(adapter, account_id, principal)
    validation = validate_and_gate_snapshot(account_summary, account_positions)
    active_id = require_single_account_id(account_id, account_summary.account_id, adapter)
    policy = get_portfolio_policy(active_id, user_id=tenant_user_id(principal))
    profile = get_investor_profile(active_id, user_id=tenant_user_id(principal))
    result = generate_rebalance_proposal(account_positions, account_summary, policy, profile)
    return prepare_professional_response(result, account_summary, account_positions, validation)


@router.get("/optimization-proposal")
def optimize_portfolio(
    account_id: Optional[str] = None,
    objective: str = "min_variance",
    adapter: BrokerAdapter = Depends(get_broker_adapter),
    principal: Principal = Depends(get_current_principal),
):
    from app.services.policy.engine import get_portfolio_policy
    from app.services.portfolio_construction.optimizer import generate_portfolio_optimization
    from app.services.portfolio.account_scope import require_single_account_id
    from app.services.suitability.engine import get_investor_profile

    account_summary, account_positions = _resolve_account_data(adapter, account_id, principal)
    validation = validate_and_gate_snapshot(account_summary, account_positions)
    active_id = require_single_account_id(account_id, account_summary.account_id, adapter)
    policy = get_portfolio_policy(active_id, user_id=tenant_user_id(principal))
    profile = get_investor_profile(active_id, user_id=tenant_user_id(principal))
    result = generate_portfolio_optimization(
        account_positions,
        account_summary,
        policy,
        profile,
        objective=objective,
    )
    return prepare_professional_response(result, account_summary, account_positions, validation)


@router.get("/fundamentals/{symbol}/point-in-time")
def point_in_time_fundamentals(symbol: str, as_of: Optional[str] = None):
    from datetime import date as date_type

    from fastapi import HTTPException

    from app.core.config import settings
    from app.services.fundamentals.providers import get_fundamental_provider
    from app.services.fundamentals.snapshot_store import get_point_in_time_fundamentals, seed_demo_fundamentals_records

    as_of_date = date_type.fromisoformat(as_of) if as_of else date_type.today()
    allow_demo = settings.broker_mode == "mock_ibkr_readonly"
    snapshot = get_point_in_time_fundamentals(symbol, as_of_date, allow_synthetic_demo=allow_demo)
    if snapshot is None and allow_demo:
        base = get_fundamental_provider(allow_mock=True).get_fundamentals(symbol)
        seed_demo_fundamentals_records(symbol, base)
        snapshot = get_point_in_time_fundamentals(symbol, as_of_date, allow_synthetic_demo=True)
    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "PIT_FUNDAMENTALS_UNAVAILABLE",
                "message": f"No genuine point-in-time fundamentals for {symbol.upper()} on {as_of_date.isoformat()}",
            },
        )
    return {
        "symbol": symbol.upper(),
        "as_of_date": as_of_date.isoformat(),
        "snapshot": snapshot,
        "point_in_time": snapshot.source != "synthetic_demo",
        "synthetic_demo": snapshot.source == "synthetic_demo",
    }
