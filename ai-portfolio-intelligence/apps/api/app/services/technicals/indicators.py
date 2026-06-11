from datetime import datetime, timezone

from app.schemas.domain import TechnicalIndicators


def _sma(values: list[float], window: int) -> float:
    if len(values) < window:
        raise ValueError(f"Need at least {window} prices")
    return sum(values[-window:]) / window


def _ema(values: list[float], window: int) -> float:
    if len(values) < window:
        raise ValueError(f"Need at least {window} prices")
    multiplier = 2 / (window + 1)
    ema = sum(values[:window]) / window
    for value in values[window:]:
        ema = (value - ema) * multiplier + ema
    return ema


def _rsi(values: list[float], window: int = 14) -> float:
    if len(values) <= window:
        raise ValueError("Need more prices for RSI")
    gains: list[float] = []
    losses: list[float] = []
    for previous, current in zip(values[-window - 1 : -1], values[-window:]):
        change = current - previous
        gains.append(max(change, 0))
        losses.append(abs(min(change, 0)))
    avg_gain = sum(gains) / window
    avg_loss = sum(losses) / window
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _trend(price: float, sma_20: float, sma_50: float, sma_200: float) -> str:
    if price > sma_20 > sma_50 > sma_200:
        return "strong uptrend"
    if price > sma_50 > sma_200:
        return "uptrend"
    if price < sma_50 < sma_200:
        return "downtrend"
    if price < sma_200:
        return "weakening"
    return "neutral"


def calculate_technical_indicators(symbol: str, prices: list[float]) -> TechnicalIndicators:
    if len(prices) < 200:
        raise ValueError("At least 200 daily closes are required for full technical analysis")

    sma_20 = _sma(prices, 20)
    sma_50 = _sma(prices, 50)
    sma_100 = _sma(prices, 100)
    sma_200 = _sma(prices, 200)
    ema_8 = _ema(prices, 8)
    ema_21 = _ema(prices, 21)
    macd = _ema(prices, 12) - _ema(prices, 26)
    signal_seed = [_ema(prices[: index], 12) - _ema(prices[: index], 26) for index in range(35, len(prices) + 1)]
    macd_signal = _ema(signal_seed, 9)
    high_52w = max(prices[-252:]) if len(prices) >= 252 else max(prices)
    drawdown = (prices[-1] - high_52w) / high_52w * 100
    return TechnicalIndicators(
        symbol=symbol,
        date=datetime.now(timezone.utc).date(),
        sma_20=round(sma_20, 2),
        sma_50=round(sma_50, 2),
        sma_100=round(sma_100, 2),
        sma_200=round(sma_200, 2),
        ema_8=round(ema_8, 2),
        ema_21=round(ema_21, 2),
        rsi_14=round(_rsi(prices), 2),
        macd=round(macd, 2),
        macd_signal=round(macd_signal, 2),
        macd_histogram=round(macd - macd_signal, 2),
        # These metrics require high/low, volume, and aligned benchmark returns.
        # A close-only series cannot calculate them accurately.
        atr_14=None,
        beta=None,
        volume_ratio=None,
        relative_strength_spy=None,
        relative_strength_qqq=None,
        drawdown_from_52w_high=round(drawdown, 2),
        trend_classification=_trend(prices[-1], sma_20, sma_50, sma_200),
    )
