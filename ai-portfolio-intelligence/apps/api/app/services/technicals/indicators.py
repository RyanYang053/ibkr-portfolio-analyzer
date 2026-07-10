from __future__ import annotations

import math
from datetime import datetime, timezone

from app.schemas.domain import TechnicalIndicators


def _validated_prices(values: list[float], minimum: int = 1) -> list[float]:
    if len(values) < minimum:
        raise ValueError(f"Need at least {minimum} prices")

    cleaned: list[float] = []
    for index, raw in enumerate(values):
        if isinstance(raw, bool):
            raise ValueError(f"Price at index {index} is not numeric")
        value = float(raw)
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"Price at index {index} must be finite and greater than zero")
        cleaned.append(value)
    return cleaned


def _sma(values: list[float], window: int) -> float:
    if len(values) < window:
        raise ValueError(f"Need at least {window} prices")
    return sum(values[-window:]) / window


def _ema_series(values: list[float], window: int) -> list[float]:
    if window <= 0:
        raise ValueError("EMA window must be positive")
    if len(values) < window:
        raise ValueError(f"Need at least {window} prices")

    multiplier = 2.0 / (window + 1.0)
    ema = sum(values[:window]) / window
    series = [ema]
    for value in values[window:]:
        ema += multiplier * (value - ema)
        series.append(ema)
    return series


def _ema(values: list[float], window: int) -> float:
    return _ema_series(values, window)[-1]


def _rsi(values: list[float], window: int = 14) -> float:
    if window <= 0:
        raise ValueError("RSI window must be positive")
    if len(values) <= window:
        raise ValueError(f"Need at least {window + 1} prices for RSI")

    changes = [current - previous for previous, current in zip(values, values[1:])]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]

    average_gain = sum(gains[:window]) / window
    average_loss = sum(losses[:window]) / window
    for gain, loss in zip(gains[window:], losses[window:]):
        average_gain = ((window - 1) * average_gain + gain) / window
        average_loss = ((window - 1) * average_loss + loss) / window

    if average_gain == 0 and average_loss == 0:
        return 50.0
    if average_loss == 0:
        return 100.0
    if average_gain == 0:
        return 0.0

    relative_strength = average_gain / average_loss
    return 100.0 - (100.0 / (1.0 + relative_strength))


def _macd(values: list[float]) -> tuple[float, float, float]:
    # Align the 12-day EMA series with the 26-day EMA series before calculating
    # the 9-period signal EMA. This avoids the O(n^2), slice-dependent signal
    # calculation that previously biased the result.
    fast = _ema_series(values, 12)
    slow = _ema_series(values, 26)
    fast_offset = 26 - 12
    aligned_fast = fast[fast_offset:]
    macd_series = [fast_value - slow_value for fast_value, slow_value in zip(aligned_fast, slow)]
    if len(macd_series) < 9:
        raise ValueError("Need enough prices to calculate the MACD signal")
    signal = _ema(macd_series, 9)
    macd = macd_series[-1]
    return macd, signal, macd - signal


def _trend(price: float, sma_20: float, sma_50: float, sma_200: float) -> str:
    if price > sma_20 > sma_50 > sma_200:
        return "strong uptrend"
    if price > sma_50 > sma_200:
        return "uptrend"
    if price < sma_20 < sma_50 < sma_200:
        return "strong downtrend"
    if price < sma_50 < sma_200:
        return "downtrend"
    if price < sma_200:
        return "weakening"
    return "neutral"


def calculate_technical_indicators(symbol: str, prices: list[float]) -> TechnicalIndicators:
    cleaned = _validated_prices(prices, minimum=200)

    sma_20 = _sma(cleaned, 20)
    sma_50 = _sma(cleaned, 50)
    sma_100 = _sma(cleaned, 100)
    sma_200 = _sma(cleaned, 200)
    ema_8 = _ema(cleaned, 8)
    ema_21 = _ema(cleaned, 21)
    macd, macd_signal, macd_histogram = _macd(cleaned)
    high_52w = max(cleaned[-252:])
    drawdown = (cleaned[-1] / high_52w - 1.0) * 100.0

    return TechnicalIndicators(
        symbol=symbol.upper().strip(),
        date=datetime.now(timezone.utc).date(),
        sma_20=round(sma_20, 4),
        sma_50=round(sma_50, 4),
        sma_100=round(sma_100, 4),
        sma_200=round(sma_200, 4),
        ema_8=round(ema_8, 4),
        ema_21=round(ema_21, 4),
        rsi_14=round(_rsi(cleaned), 4),
        macd=round(macd, 4),
        macd_signal=round(macd_signal, 4),
        macd_histogram=round(macd_histogram, 4),
        # These metrics require high/low, volume, and aligned benchmark returns.
        # A close-only series cannot calculate them accurately.
        atr_14=None,
        beta=None,
        volume_ratio=None,
        relative_strength_spy=None,
        relative_strength_qqq=None,
        drawdown_from_52w_high=round(drawdown, 4),
        trend_classification=_trend(cleaned[-1], sma_20, sma_50, sma_200),
    )
