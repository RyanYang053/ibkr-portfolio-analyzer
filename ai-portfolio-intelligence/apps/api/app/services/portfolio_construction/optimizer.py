from __future__ import annotations

import math
from collections import defaultdict

from app.schemas.domain import (
    AccountSummary,
    InvestmentPolicyStatement,
    InvestorProfile,
    PortfolioOptimizationItem,
    PortfolioOptimizationProposal,
    Position,
)
from app.services.policy.engine import analyze_policy_drift

MINIMUM_TRADE_VALUE = 100.0


def _invert_matrix(matrix: list[list[float]]) -> list[list[float]] | None:
    size = len(matrix)
    augmented = [row[:] + [1.0 if index == row_index else 0.0 for index in range(size)] for row_index, row in enumerate(matrix)]
    for pivot in range(size):
        diag = augmented[pivot][pivot]
        if abs(diag) < 1e-12:
            return None
        for col in range(2 * size):
            augmented[pivot][col] /= diag
        for row in range(size):
            if row == pivot:
                continue
            factor = augmented[row][pivot]
            if factor == 0:
                continue
            for col in range(2 * size):
                augmented[row][col] -= factor * augmented[pivot][col]
    return [row[size:] for row in augmented]


def _covariance_matrix(returns_by_symbol: dict[str, list[float]]) -> tuple[list[str], list[list[float]]]:
    symbols = sorted(returns_by_symbol)
    length = min(len(returns_by_symbol[symbol]) for symbol in symbols)
    if length < 5:
        return [], []
    matrix = [[0.0 for _ in symbols] for _ in symbols]
    for i, left in enumerate(symbols):
        left_returns = returns_by_symbol[left][-length:]
        left_mean = sum(left_returns) / length
        for j, right in enumerate(symbols):
            right_returns = returns_by_symbol[right][-length:]
            right_mean = sum(right_returns) / length
            covariance = sum(
                (left_returns[index] - left_mean) * (right_returns[index] - right_mean)
                for index in range(length)
            ) / max(length - 1, 1)
            matrix[i][j] = covariance
    return symbols, matrix


def _project_weights(
    symbols: list[str],
    weights: list[float],
    policy: InvestmentPolicyStatement,
    sectors: dict[str, str],
) -> list[float]:
    projected = weights[:]
    for _ in range(8):
        for index, symbol in enumerate(symbols):
            projected[index] = min(projected[index], policy.max_single_stock_weight / 100.0)
            projected[index] = max(projected[index], 0.0)
        sector_totals: dict[str, float] = defaultdict(float)
        for index, symbol in enumerate(symbols):
            sector_totals[sectors.get(symbol, "Unknown")] += projected[index]
        sector_cap = policy.max_sector_weight / 100.0
        for sector, total in sector_totals.items():
            if total <= sector_cap or total <= 0:
                continue
            scale = sector_cap / total
            for index, symbol in enumerate(symbols):
                if sectors.get(symbol, "Unknown") == sector:
                    projected[index] *= scale
        total = sum(projected)
        if total <= 0:
            break
        cash_target = policy.target_cash_percent / 100.0
        equity_scale = min(1.0, max(0.0, 1.0 - cash_target) / total)
        projected = [weight * equity_scale for weight in projected]
    return projected


def generate_portfolio_optimization(
    positions: list[Position],
    summary: AccountSummary,
    policy: InvestmentPolicyStatement,
    profile: InvestorProfile,
    *,
    objective: str = "min_variance",
) -> PortfolioOptimizationProposal:
    from datetime import date, timedelta

    from app.services.broker.ibkr_readonly import get_exchange_rate
    from app.services.market_data.mock_provider import MockMarketDataProvider
    from app.services.risk.history_reconstructor import reconstruct_portfolio_history

    allow_mock = summary.account_id.startswith("MOCK")
    total_value = float(summary.net_liquidation)
    if total_value <= 0:
        raise ValueError("Net liquidation must be positive before optimization")

    long_positions = [
        position
        for position in positions
        if position.quantity > 0 and position.asset_class not in {"OPT", "FOP"} and not position.is_speculative
    ]
    if len(long_positions) < 2:
        raise ValueError("At least two long equity positions are required for optimization")

    provider = MockMarketDataProvider(allow_mock=allow_mock)
    end_date = date.today()
    start_date = end_date - timedelta(days=400)
    returns_by_symbol: dict[str, list[float]] = {}
    sectors: dict[str, str] = {}
    converted_values: dict[str, float] = {}
    for position in long_positions:
        history = provider.get_historical_prices(position.symbol, start_date, end_date, total_return=True)
        closes = {str(item["date"]): float(item["close"]) for item in history if item.get("close")}
        dates = sorted(closes)
        daily = []
        for left, right in zip(dates, dates[1:]):
            if closes[left] > 0:
                daily.append((closes[right] / closes[left]) - 1.0)
        if len(daily) >= 5:
            returns_by_symbol[position.symbol] = daily
            sectors[position.symbol] = position.sector or "Unknown"
            converted_values[position.symbol] = abs(
                position.market_value * get_exchange_rate(position.currency, summary.base_currency)
            )

    symbols, covariance = _covariance_matrix(returns_by_symbol)
    if not symbols:
        raise ValueError("Insufficient return history to optimize portfolio weights")

    inverse = _invert_matrix(covariance)
    if inverse is None:
        raise ValueError("Covariance matrix is not invertible")

    ones = [1.0 for _ in symbols]
    inv_ones = [sum(inverse[row][col] * ones[col] for col in range(len(symbols))) for row in range(len(symbols))]
    denominator = sum(ones[index] * inv_ones[index] for index in range(len(symbols)))
    if denominator <= 0:
        raise ValueError("Unable to solve minimum-variance weights")
    raw_weights = [value / denominator for value in inv_ones]
    optimal_weights = _project_weights(symbols, raw_weights, policy, sectors)

    drift = analyze_policy_drift(
        positions,
        summary.cash,
        total_value,
        policy,
        base_currency=summary.base_currency,
        fx_resolver=get_exchange_rate,
    )

    proposed_trades: list[PortfolioOptimizationItem] = []
    for index, symbol in enumerate(symbols):
        current_value = converted_values.get(symbol, 0.0)
        current_weight = current_value / total_value * 100.0
        target_weight = optimal_weights[index] * 100.0
        target_value = total_value * optimal_weights[index]
        delta_value = target_value - current_value
        position = next(item for item in long_positions if item.symbol == symbol)
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
                    f"Minimum-variance target weight {target_weight:.2f}% "
                    f"versus current {current_weight:.2f}%."
                ),
            )
        )

    reconstruction = reconstruct_portfolio_history(positions, summary, allow_mock=allow_mock)
    expected_vol = None
    expected_return = None
    sharpe = None
    if reconstruction is not None:
        port_returns = reconstruction.get("port_returns") or []
        if len(port_returns) >= 5:
            mean_daily = sum(port_returns) / len(port_returns)
            variance = sum((value - mean_daily) ** 2 for value in port_returns) / max(len(port_returns) - 1, 1)
            expected_vol = round(math.sqrt(variance) * math.sqrt(252) * 100.0, 2)
            expected_return = round(((1.0 + mean_daily) ** 252 - 1.0) * 100.0, 2)
            if expected_vol and expected_vol > 0:
                sharpe = round(expected_return / expected_vol, 2)

    constraints = [
        f"max_single_stock_weight={policy.max_single_stock_weight:.2f}%",
        f"max_sector_weight={policy.max_sector_weight:.2f}%",
        f"target_cash={policy.target_cash_percent:.2f}%",
        f"restricted_symbols={','.join(profile.restrictions) or 'none'}",
    ]
    if drift.get("rebalance_triggered"):
        constraints.append("policy_drift_triggered=true")

    return PortfolioOptimizationProposal(
        objective=objective,
        proposed_trades=proposed_trades,
        expected_volatility=expected_vol,
        expected_return=expected_return,
        sharpe_ratio=sharpe,
        constraints_applied=constraints,
        methodology=(
            "Mean-variance optimization on historical daily total returns with policy projection "
            "for single-name and sector caps. Output is a review proposal only; taxes, spreads, "
            "and liquidity are not modeled."
        ),
    )
