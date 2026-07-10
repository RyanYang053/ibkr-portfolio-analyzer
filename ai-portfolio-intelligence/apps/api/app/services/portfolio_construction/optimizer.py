from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

from app.schemas.domain import (
    AccountSummary,
    InvestmentPolicyStatement,
    InvestorProfile,
    PortfolioOptimizationItem,
    PortfolioOptimizationProposal,
    Position,
)
from app.services.policy.engine import analyze_policy_drift
from app.services.portfolio_construction.advanced_optimizer import InstrumentKey

MINIMUM_TRADE_VALUE = 100.0
TRADING_DAYS = 252


def _instrument_key(position: Position) -> InstrumentKey:
    return (
        position.con_id,
        position.symbol.upper(),
        (position.local_symbol or position.symbol).upper(),
        position.currency.upper(),
    )


def _instrument_label(key: InstrumentKey) -> str:
    return key[1]


def _minimum_observations(asset_count: int) -> int:
    return max(60, 3 * asset_count)


def _aligned_daily_returns(
    closes_by_instrument: dict[InstrumentKey, dict[str, float]],
    *,
    minimum_observations: int,
) -> tuple[list[InstrumentKey], dict[InstrumentKey, list[float]]]:
    instruments = sorted(closes_by_instrument)
    if not instruments:
        return [], {}

    common_dates = set(closes_by_instrument[instruments[0]].keys())
    for instrument in instruments[1:]:
        common_dates &= set(closes_by_instrument[instrument].keys())
    ordered_dates = sorted(common_dates)
    if len(ordered_dates) < minimum_observations + 1:
        return [], {}

    returns_by_instrument: dict[InstrumentKey, list[float]] = {}
    for instrument in instruments:
        daily: list[float] = []
        for left, right in zip(ordered_dates, ordered_dates[1:]):
            prior = closes_by_instrument[instrument][left]
            current = closes_by_instrument[instrument][right]
            if prior <= 0:
                return [], {}
            daily.append((current / prior) - 1.0)
        returns_by_instrument[instrument] = daily
    return instruments, returns_by_instrument


def _covariance_matrix(returns_by_instrument: dict[InstrumentKey, list[float]]) -> tuple[list[InstrumentKey], list[list[float]]]:
    instruments = sorted(returns_by_instrument)
    length = min(len(returns_by_instrument[instrument]) for instrument in instruments)
    minimum = _minimum_observations(len(instruments))
    if length < minimum:
        return [], []
    ridge = 1e-6
    matrix = [[0.0 for _ in instruments] for _ in instruments]
    for i, left in enumerate(instruments):
        left_returns = returns_by_instrument[left][-length:]
        left_mean = sum(left_returns) / length
        for j, right in enumerate(instruments):
            right_returns = returns_by_instrument[right][-length:]
            right_mean = sum(right_returns) / length
            covariance = sum(
                (left_returns[index] - left_mean) * (right_returns[index] - right_mean)
                for index in range(length)
            ) / max(length - 1, 1)
            matrix[i][j] = covariance
    for index in range(len(instruments)):
        matrix[index][index] += ridge
    return instruments, matrix


def _shrink_covariance(matrix: list[list[float]], shrinkage: float = 0.2) -> list[list[float]]:
    size = len(matrix)
    if size == 0:
        return matrix
    average_variance = sum(matrix[index][index] for index in range(size)) / size
    return [
        [
            (1.0 - shrinkage) * matrix[i][j] + (shrinkage * average_variance if i == j else 0.0)
            for j in range(size)
        ]
        for i in range(size)
    ]


def _risk_parity_weights(covariance: list[list[float]]) -> list[float] | None:
    size = len(covariance)
    if size == 0:
        return None
    volatilities = [math.sqrt(max(covariance[index][index], 1e-12)) for index in range(size)]
    inverse = [1.0 / volatility for volatility in volatilities]
    total = sum(inverse)
    if total <= 0:
        return None
    return [value / total for value in inverse]


def _annualized_means(returns_by_key: dict[InstrumentKey, list[float]], keys: list[InstrumentKey]) -> list[float]:
    return [sum(returns_by_key[key]) / len(returns_by_key[key]) * TRADING_DAYS for key in keys]


def _project_weights(
    instruments: list[InstrumentKey],
    weights: list[float],
    policy: InvestmentPolicyStatement,
    sectors: dict[InstrumentKey, str],
    etf_instruments: set[InstrumentKey],
) -> list[float]:
    projected = weights[:]
    for _ in range(8):
        for index, instrument in enumerate(instruments):
            if instrument not in etf_instruments:
                projected[index] = min(projected[index], policy.max_single_stock_weight / 100.0)
            projected[index] = max(projected[index], 0.0)
        sector_totals: dict[str, float] = defaultdict(float)
        for index, instrument in enumerate(instruments):
            sector_totals[sectors.get(instrument, "Unknown")] += projected[index]
        sector_cap = policy.max_sector_weight / 100.0
        for sector, total in sector_totals.items():
            if total <= sector_cap or total <= 0:
                continue
            scale = sector_cap / total
            for index, instrument in enumerate(instruments):
                if sectors.get(instrument, "Unknown") == sector:
                    projected[index] *= scale
        total = sum(projected)
        if total <= 0:
            break
        projected = [weight / total for weight in projected]
    return projected


def _portfolio_cap_to_sleeve_relative(portfolio_cap: float, sleeve_portfolio_fraction: float) -> float:
    if sleeve_portfolio_fraction <= 0:
        return portfolio_cap
    return portfolio_cap / sleeve_portfolio_fraction


def _per_asset_sleeve_caps(
    instruments: list[InstrumentKey],
    *,
    policy: InvestmentPolicyStatement,
    etf_instruments: set[InstrumentKey],
    sleeve_portfolio_fraction: float,
    liquidity_portfolio_cap: float,
) -> np.ndarray:
    caps: list[float] = []
    for instrument in instruments:
        if instrument in etf_instruments:
            portfolio_cap = 1.0
        else:
            portfolio_cap = policy.max_single_stock_weight / 100.0
        portfolio_cap = min(portfolio_cap, liquidity_portfolio_cap)
        caps.append(_portfolio_cap_to_sleeve_relative(portfolio_cap, sleeve_portfolio_fraction))
    return np.array(caps, dtype=float)


def _is_optimizable(position: Position, restrictions: set[str]) -> bool:
    if position.quantity <= 0:
        return False
    if position.asset_class in {"OPT", "FOP"}:
        return False
    if position.is_speculative:
        return False
    if position.symbol.upper() in restrictions:
        return False
    return True


def generate_portfolio_optimization(
    positions: list[Position],
    summary: AccountSummary,
    policy: InvestmentPolicyStatement,
    profile: InvestorProfile,
    *,
    objective: str = "min_variance",
) -> PortfolioOptimizationProposal:
    from datetime import date, timedelta

    from app.core.config import settings
    from app.services.broker.ibkr_readonly import get_exchange_rate
    from app.services.market_data.mock_provider import MockMarketDataProvider

    if objective not in {"min_variance", "risk_parity", "hrp", "black_litterman", "cvar"}:
        raise ValueError("Supported objectives: min_variance, risk_parity, hrp, black_litterman, cvar")

    allow_mock = summary.account_id.startswith("MOCK")
    experimental_objectives = {"risk_parity", "hrp", "black_litterman", "cvar"}
    if objective in experimental_objectives and not allow_mock:
        raise ValueError(
            f"Objective '{objective}' is experimental and withheld outside mock/demo portfolios."
        )
    total_value = float(summary.net_liquidation)
    if total_value <= 0:
        raise ValueError("Net liquidation must be positive before optimization")

    restrictions = {symbol.upper() for symbol in profile.restrictions}
    optimizable_positions = [position for position in positions if _is_optimizable(position, restrictions)]
    if len(optimizable_positions) < 2:
        raise ValueError("At least two optimizable long equity positions are required for optimization")

    provider = MockMarketDataProvider(allow_mock=allow_mock)
    end_date = date.today()
    start_date = end_date - timedelta(days=500)
    closes_by_instrument: dict[InstrumentKey, dict[str, float]] = {}
    sectors: dict[InstrumentKey, str] = {}
    etf_instruments: set[InstrumentKey] = set()
    converted_values: dict[InstrumentKey, float] = {}

    for position in optimizable_positions:
        instrument = _instrument_key(position)
        history = provider.get_historical_prices(position.symbol, start_date, end_date, total_return=True)
        closes = {
            str(item["date"]): float(item["close"])
            for item in history
            if item.get("close") is not None and float(item["close"]) > 0
        }
        if not closes:
            continue
        closes_by_instrument[instrument] = closes
        sectors[instrument] = position.sector or "Unknown"
        if position.is_etf:
            etf_instruments.add(instrument)
        converted_values[instrument] = abs(
            position.market_value * get_exchange_rate(position.currency, summary.base_currency)
        )

    covariance_instruments, returns_by_instrument = _aligned_daily_returns(
        closes_by_instrument,
        minimum_observations=_minimum_observations(len(closes_by_instrument)),
    )
    if not covariance_instruments:
        raise ValueError("Insufficient date-aligned return history to optimize portfolio weights")

    covariance_symbols, covariance = _covariance_matrix(returns_by_instrument)
    if not covariance_symbols:
        raise ValueError("Insufficient return history to optimize portfolio weights")

    covariance = _shrink_covariance(covariance)

    cash_target = policy.target_cash_percent / 100.0
    modeled_keys = {
        _instrument_key(position)
        for position in optimizable_positions
        if _instrument_key(position) in covariance_symbols
    }
    fixed_weight = 0.0
    fixed_sector_exposure: dict[str, float] = defaultdict(float)
    for position in positions:
        if _instrument_key(position) in modeled_keys:
            continue
        rate = get_exchange_rate(position.currency, summary.base_currency)
        position_weight = abs(position.market_value * rate) / total_value
        fixed_weight += position_weight
        fixed_sector_exposure[position.sector or "Unknown"] += position_weight

    sleeve_budget = max(0.0, 1.0 - cash_target - fixed_weight)
    if sleeve_budget <= 0:
        raise ValueError("No optimizable sleeve remains after reserving cash and fixed holdings")

    optimizable_current_weight = sum(converted_values.get(instrument, 0.0) for instrument in covariance_symbols) / total_value
    current_sleeve_weights = [
        (
            converted_values.get(instrument, 0.0) / total_value / optimizable_current_weight
            if optimizable_current_weight > 0
            else 0.0
        )
        for instrument in covariance_symbols
    ]
    sector_labels = [sectors.get(instrument, "Unknown") for instrument in covariance_symbols]
    sector_cap = policy.max_sector_weight / 100.0
    per_asset_caps = _per_asset_sleeve_caps(
        covariance_symbols,
        policy=policy,
        etf_instruments=etf_instruments,
        sleeve_portfolio_fraction=sleeve_budget,
        liquidity_portfolio_cap=settings.optimization_liquidity_cap,
    )
    turnover_budget = settings.optimization_turnover_budget
    if profile.account_type == "Taxable":
        turnover_budget = min(turnover_budget, 0.15)
    solver_metadata: dict[str, object] = {}
    used_cvxpy_solver = False

    if objective == "risk_parity":
        raw_weights = _risk_parity_weights(covariance)
        if raw_weights is None:
            raise ValueError("Unable to solve risk-parity weights")
    elif objective == "hrp":
        from app.services.portfolio_construction.advanced_optimizer import hierarchical_risk_parity_weights

        raw_weights = hierarchical_risk_parity_weights(covariance)
        if raw_weights is None:
            raise ValueError("Unable to solve HRP weights")
        solver_metadata["method"] = "hierarchical_risk_parity"
    elif objective == "black_litterman":
        from app.services.portfolio_construction.advanced_optimizer import (
            black_litterman_posterior_returns,
            solve_mean_variance_with_constraints,
        )

        posterior = black_litterman_posterior_returns(covariance, current_sleeve_weights)
        raw_weights, solver_metadata = solve_mean_variance_with_constraints(
            covariance,
            posterior,
            sleeve_budget=1.0,
            current_weights=current_sleeve_weights,
            turnover_budget=turnover_budget,
            max_weights=per_asset_caps,
            sector_labels=sector_labels,
            sector_cap=sector_cap,
            fixed_sector_exposure=dict(fixed_sector_exposure),
            sleeve_portfolio_fraction=sleeve_budget,
        )
        if raw_weights is None:
            raise ValueError("Black-Litterman optimization failed")
        feasibility = solver_metadata.get("feasibility", {})
        if not feasibility.get("feasible"):
            raise ValueError(f"Optimizer returned infeasible weights: {feasibility.get('violations')}")
        solver_metadata["method"] = "black_litterman"
        used_cvxpy_solver = True
    elif objective == "cvar":
        from app.services.portfolio_construction.advanced_optimizer import solve_cvar_weights

        raw_weights, solver_metadata = solve_cvar_weights(
            {_instrument_label(key): returns_by_instrument[key] for key in covariance_symbols},
            [_instrument_label(key) for key in covariance_symbols],
            current_weights=current_sleeve_weights,
            turnover_budget=turnover_budget,
            max_weights=per_asset_caps,
            sector_labels=sector_labels,
            sector_cap=sector_cap,
            fixed_sector_exposure=dict(fixed_sector_exposure),
            sleeve_portfolio_fraction=sleeve_budget,
        )
        if raw_weights is None:
            raise ValueError("CVaR optimization failed")
        feasibility = solver_metadata.get("feasibility", {})
        if not feasibility.get("feasible"):
            raise ValueError(f"Optimizer returned infeasible weights: {feasibility.get('violations')}")
        solver_metadata["method"] = "cvar"
        used_cvxpy_solver = True
    else:
        from app.services.portfolio_construction.advanced_optimizer import (
            OptimizationConstraints,
            solve_min_variance_with_constraints,
        )

        optimization_constraints = OptimizationConstraints(
            sleeve_budget=1.0,
            current_weights=np.array(current_sleeve_weights, dtype=float),
            turnover_budget=turnover_budget,
            liquidity_caps=None,
            max_weights=per_asset_caps,
            sector_labels=sector_labels,
            sector_cap=sector_cap,
            fixed_sector_exposure=dict(fixed_sector_exposure),
            sleeve_portfolio_fraction=sleeve_budget,
        )
        raw_weights, solver_metadata = solve_min_variance_with_constraints(covariance, optimization_constraints)
        if raw_weights is None:
            raise ValueError(f"Minimum-variance optimization failed: {solver_metadata.get('status')}")
        feasibility = solver_metadata.get("feasibility", {})
        if not feasibility.get("feasible"):
            raise ValueError(f"Optimizer returned infeasible weights: {feasibility.get('violations')}")
        used_cvxpy_solver = True
        solver_metadata["method"] = "min_variance_constrained"

    if used_cvxpy_solver:
        sleeve_weights = [max(0.0, weight) for weight in raw_weights]
    else:
        sleeve_weights = _project_weights(covariance_symbols, raw_weights, policy, sectors, etf_instruments)
    sleeve_sum = sum(sleeve_weights)
    if sleeve_sum <= 0:
        raise ValueError("Optimized sleeve weights collapsed to zero")
    sleeve_weights = [weight / sleeve_sum * sleeve_budget for weight in sleeve_weights]

    full_weights = {instrument: weight for instrument, weight in zip(covariance_symbols, sleeve_weights)}
    for position in positions:
        if _instrument_key(position) in modeled_keys:
            continue
        rate = get_exchange_rate(position.currency, summary.base_currency)
        full_weights.setdefault(_instrument_key(position), abs(position.market_value * rate) / total_value)

    drift = analyze_policy_drift(
        positions,
        summary.cash,
        total_value,
        policy,
        base_currency=summary.base_currency,
        fx_resolver=get_exchange_rate,
    )

    proposed_trades: list[PortfolioOptimizationItem] = []
    for index, instrument in enumerate(covariance_symbols):
        symbol = _instrument_label(instrument)
        current_value = converted_values.get(instrument, 0.0)
        current_weight = current_value / total_value * 100.0
        target_weight = sleeve_weights[index] * 100.0
        target_value = total_value * sleeve_weights[index]
        delta_value = target_value - current_value
        position = next(item for item in optimizable_positions if _instrument_key(item) == instrument)
        market_price_base = position.market_price * get_exchange_rate(position.currency, summary.base_currency)
        if abs(delta_value) < MINIMUM_TRADE_VALUE:
            action = "Hold"
            trade_qty = 0.0
            trade_value = 0.0
        elif delta_value > 0:
            action = "Buy"
            trade_value = delta_value
            trade_qty = trade_value / market_price_base if market_price_base > 0 else 0.0
        else:
            action = "Sell"
            trade_value = delta_value
            trade_qty = trade_value / market_price_base if market_price_base > 0 else 0.0
        proposed_trades.append(
            PortfolioOptimizationItem(
                symbol=symbol,
                current_weight=round(current_weight, 2),
                optimal_weight=round(target_weight, 2),
                current_value=round(current_value, 2),
                proposed_trade_value=round(trade_value, 2),
                proposed_trade_qty=round(trade_qty, 6),
                action=action,
                reason=(
                    f"{objective.replace('_', ' ')} sleeve target {target_weight:.2f}% "
                    f"versus current {current_weight:.2f}%."
                ),
            )
        )

    annual_means = _annualized_means(returns_by_instrument, covariance_symbols)
    weight_vector = [full_weights.get(instrument, 0.0) for instrument in covariance_symbols]
    expected_return_annual = sum(weight * mean for weight, mean in zip(weight_vector, annual_means))
    variance = 0.0
    for i, left in enumerate(covariance_symbols):
        for j, right in enumerate(covariance_symbols):
            variance += weight_vector[i] * covariance[i][j] * weight_vector[j] * TRADING_DAYS
    expected_vol_annual = math.sqrt(max(variance, 0.0))
    risk_free_rate = float(getattr(settings, "risk_free_rate_annual", 0.0))
    sharpe = None
    if expected_vol_annual > 0:
        sharpe = (expected_return_annual - risk_free_rate) / expected_vol_annual

    modeled_coverage = (
        sum(converted_values.get(instrument, 0.0) for instrument in covariance_symbols) / total_value * 100.0
    )

    feasibility = solver_metadata.get("feasibility", {}) if used_cvxpy_solver else {}
    constraints = [
        f"objective={objective}",
        f"solver={solver_metadata.get('method', objective)}",
        f"solver_status={solver_metadata.get('status', 'analytic')}",
        f"max_single_stock_weight={policy.max_single_stock_weight:.2f}% (stocks only)",
        f"max_sector_weight={policy.max_sector_weight:.2f}%",
        f"target_cash={policy.target_cash_percent:.2f}%",
        f"fixed_sleeve_reserved={fixed_weight * 100.0:.2f}%",
        f"optimizable_sleeve={sleeve_budget * 100.0:.2f}%",
        f"restricted_symbols={','.join(profile.restrictions) or 'none'}",
    ]
    if used_cvxpy_solver and feasibility.get("feasible"):
        constraints.append(f"turnover_budget={turnover_budget:.2f}")
        constraints.append("post_solve_feasible=true")
    elif used_cvxpy_solver:
        constraints.append(f"post_solve_feasible={feasibility.get('feasible', False)}")
    if profile.account_type == "Taxable":
        constraints.append("tax_aware_turnover_cap=true")
    if drift.get("rebalance_triggered"):
        constraints.append("policy_drift_triggered=true")

    return PortfolioOptimizationProposal(
        objective=objective,
        proposed_trades=proposed_trades,
        expected_volatility=None,
        expected_return=None,
        sharpe_ratio=None,
        modeled_sleeve_expected_volatility=round(expected_vol_annual * 100.0, 2) if expected_vol_annual else None,
        modeled_sleeve_expected_return=round(expected_return_annual * 100.0, 2),
        modeled_sleeve_sharpe=round(sharpe, 2) if sharpe is not None else None,
        modeled_portfolio_coverage_percent=round(modeled_coverage, 2),
        constraints_applied=constraints,
        methodology=(
            "Mean-variance or inverse-volatility risk-parity optimization on date-aligned historical daily total returns "
            "with fixed-intensity diagonal-target covariance shrinkage. Cash, derivatives, speculative "
            "holdings, restricted symbols, and positions without return history are reserved outside the optimizable "
            "sleeve. Production minimum-variance proposals are solved with turnover, liquidity, sector, and "
            "single-name caps enforced in the solver and revalidated post-solve. Displayed metrics are modeled-sleeve "
            "ex-ante estimates (w^T mu, sqrt(w^T Sigma w), Sharpe with risk-free rate). Output is a review proposal only."
        ),
    )
