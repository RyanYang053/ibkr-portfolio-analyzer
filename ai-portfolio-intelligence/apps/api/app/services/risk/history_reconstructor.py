import re
import math
import sys
from datetime import date, timedelta
from typing import Any, Optional
from concurrent.futures import ThreadPoolExecutor

from app.schemas.domain import AccountSummary, Position
from app.services.market_data.mock_provider import MockMarketDataProvider
from app.core.config import settings

def get_underlying_symbol(symbol: str) -> str:
    """Extract standard stock ticker from option ticker formats (e.g. AAPL260619C00150000 or AAPL  260619C00150000)."""
    match = re.match(r"^([A-Za-z]+)", symbol.strip())
    if match:
        return match.group(1).upper()
    return symbol.upper()

def fetch_symbol_history_safe(
    provider: MockMarketDataProvider,
    symbol: str,
    start_date: date,
    end_date: date
) -> list[dict[str, Any]]:
    """Fetch history for a symbol and return empty list on failure."""
    try:
        return provider.get_historical_prices(symbol, start_date, end_date)
    except Exception:
        return []

def reconstruct_portfolio_history(
    positions: list[Position],
    summary: AccountSummary,
    allow_mock: Optional[bool] = None
) -> Optional[dict[str, Any]]:
    """
    Fetches 1-year history for all holdings and benchmarks, aligns dates,
    and returns reconstructed portfolio return/price series.
    Returns None if benchmark history (SPY) cannot be loaded, or if any active position fails.
    """
    provider = MockMarketDataProvider(allow_mock=allow_mock)
    
    end_date = date.today()
    start_date = end_date - timedelta(days=365)
    
    # 1. Fetch benchmark SPY and QQQ history
    spy_raw = fetch_symbol_history_safe(provider, "SPY", start_date, end_date)
    if not spy_raw:
        return None
        
    qqq_raw = fetch_symbol_history_safe(provider, "QQQ", start_date, end_date)
    
    # 2. Extract trading dates based on SPY benchmark
    trading_dates = sorted([day["date"] for day in spy_raw])
    if len(trading_dates) < 2:
        return None
        
    spy_prices = {day["date"]: day["close"] for day in spy_raw}
    qqq_prices = {day["date"]: day["close"] for day in qqq_raw}
    
    # Fill missing values for QQQ
    aligned_qqq = []
    for d in trading_dates:
        if d in qqq_prices:
            aligned_qqq.append(qqq_prices[d])
        else:
            prev_dates = [x for x in trading_dates if x < d and x in qqq_prices]
            if prev_dates:
                aligned_qqq.append(qqq_prices[prev_dates[-1]])
            else:
                next_dates = [x for x in trading_dates if x > d and x in qqq_prices]
                if next_dates:
                    aligned_qqq.append(qqq_prices[next_dates[0]])
                else:
                    aligned_qqq.append(1.0)
                    
    # 3. Fetch holdings history concurrently
    active_positions = [pos for pos in positions if pos.quantity > 0]
    holdings_raw: dict[str, list[dict[str, Any]]] = {}
    
    if active_positions:
        with ThreadPoolExecutor(max_workers=min(len(active_positions) + 1, 10)) as executor:
            futures = {
                pos.symbol: executor.submit(fetch_symbol_history_safe, provider, pos.symbol, start_date, end_date)
                for pos in active_positions
            }
            for symbol, future in futures.items():
                holdings_raw[symbol] = future.result()
                
    # 4. Align prices for each active position
    position_price_series: dict[str, list[float]] = {}
    for pos in active_positions:
        symbol = pos.symbol
        raw_history = holdings_raw.get(symbol, [])
        pos_prices = {p["date"]: p["close"] for p in raw_history}
        
        # If raw history is empty (e.g. failed fetch or option contract), try underlying option logic
        if not pos_prices:
            underlying = get_underlying_symbol(symbol)
            if underlying != symbol:
                underlying_raw = fetch_symbol_history_safe(provider, underlying, start_date, end_date)
                if underlying_raw:
                    underlying_prices = {p["date"]: p["close"] for p in underlying_raw}
                    
                    curr_underlying = pos.market_price
                    try:
                        curr_underlying = provider.get_latest_price(underlying)
                    except Exception:
                        pass
                    
                    for d in trading_dates:
                        if d in underlying_prices:
                            ratio = underlying_prices[d] / curr_underlying if curr_underlying > 0 else 1.0
                            pos_prices[d] = max(0.0, pos.market_price * ratio)
                            
            if not pos_prices:
                # We could not fetch any price history for an active position; abort reconstruction
                return None
                
        aligned = []
        for d in trading_dates:
            if d in pos_prices:
                aligned.append(pos_prices[d])
            else:
                prev_dates = [x for x in trading_dates if x < d and x in pos_prices]
                if prev_dates:
                    aligned.append(pos_prices[prev_dates[-1]])
                else:
                    next_dates = [x for x in trading_dates if x > d and x in pos_prices]
                    if next_dates:
                        aligned.append(pos_prices[next_dates[0]])
                    else:
                        aligned.append(pos.market_price)
        position_price_series[symbol] = aligned
        
    # 5. Reconstruct Daily Portfolio NAV
    portfolio_nav = []
    for idx, d in enumerate(trading_dates):
        daily_val = summary.cash
        for pos in active_positions:
            daily_val += pos.quantity * position_price_series[pos.symbol][idx]
        portfolio_nav.append(daily_val)
        
    # 6. Compute Returns Series
    spy_aligned_prices = [spy_prices[d] for d in trading_dates]
    
    port_returns = []
    spy_returns = []
    qqq_returns = []
    
    for t in range(1, len(trading_dates)):
        port_returns.append((portfolio_nav[t] - portfolio_nav[t-1]) / portfolio_nav[t-1])
        spy_returns.append((spy_aligned_prices[t] - spy_aligned_prices[t-1]) / spy_aligned_prices[t-1])
        qqq_returns.append((aligned_qqq[t] - aligned_qqq[t-1]) / aligned_qqq[t-1])
        
    # Individual asset returns for correlation matrix
    asset_returns: dict[str, list[float]] = {}
    for pos in active_positions:
        prices = position_price_series[pos.symbol]
        returns = []
        for t in range(1, len(prices)):
            prev = prices[t-1]
            returns.append((prices[t] - prev) / prev if prev > 0 else 0.0)
        asset_returns[pos.symbol] = returns
        
    return {
        "trading_dates": trading_dates,
        "portfolio_nav": portfolio_nav,
        "spy_prices": spy_aligned_prices,
        "port_returns": port_returns,
        "spy_returns": spy_returns,
        "qqq_returns": qqq_returns,
        "asset_returns": asset_returns,
    }

def calculate_covariance(x: list[float], y: list[float]) -> float:
    if len(x) < 2 or len(x) != len(y):
        return 0.0
    mean_x = sum(x) / len(x)
    mean_y = sum(y) / len(y)
    return sum((x_i - mean_x) * (y_i - mean_y) for x_i, y_i in zip(x, y)) / (len(x) - 1)

def calculate_variance(x: list[float]) -> float:
    return calculate_covariance(x, x)

def calculate_correlation(x: list[float], y: list[float]) -> float:
    var_x = calculate_variance(x)
    var_y = calculate_variance(y)
    if var_x <= 0 or var_y <= 0:
        return 0.0
    return calculate_covariance(x, y) / math.sqrt(var_x * var_y)
