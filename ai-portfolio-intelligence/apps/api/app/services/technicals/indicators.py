from __future__ import annotations

import math
from datetime import date, datetime, timezone

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


def _wilder_atr(highs: list[float], lows: list[float], closes: list[float], window: int = 14) -> float | None:
    if len(highs) < window + 1 or len(lows) < window + 1 or len(closes) < window + 1:
        return None
    true_ranges: list[float] = []
    for index in range(1, len(closes)):
        tr = max(
            highs[index] - lows[index],
            abs(highs[index] - closes[index - 1]),
            abs(lows[index] - closes[index - 1]),
        )
        true_ranges.append(tr)
    if len(true_ranges) < window:
        return None
    atr = sum(true_ranges[:window]) / window
    for tr in true_ranges[window:]:
        atr = ((window - 1) * atr + tr) / window
    return atr


def _normalize_bars(bars: list[dict[str, float | str]]) -> tuple[list[dict[str, float | str]], list[dict[str, float | str]]]:
    by_date: dict[str, dict[str, float | str]] = {}
    for bar in bars:
        raw_date = bar.get("date")
        if raw_date is None:
            continue
        day = str(raw_date)[:10]
        close = bar.get("close")
        if close is None:
            continue
        close_value = float(close)
        if not math.isfinite(close_value) or close_value <= 0:
            continue
        by_date[day] = {**bar, "date": day, "close": close_value}

    close_bars = [by_date[day] for day in sorted(by_date)]
    hlc_bars: list[dict[str, float | str]] = []
    for bar in close_bars:
        high = bar.get("high")
        low = bar.get("low")
        if high is None or low is None:
            continue
        high_value = float(high)
        low_value = float(low)
        close_value = float(bar["close"])
        if not math.isfinite(high_value) or not math.isfinite(low_value):
            continue
        open_value = float(bar["open"]) if bar.get("open") is not None else close_value
        if high_value < max(open_value, close_value, low_value):
            continue
        hlc_bars.append(bar)
    return close_bars, hlc_bars


def calculate_technical_indicators_from_bars(symbol: str, bars: list[dict[str, float | str]]) -> TechnicalIndicators:
    close_bars, hlc_bars = _normalize_bars(bars)
    if len(close_bars) < 252:
        raise ValueError("Need at least 252 daily closes")
    closes = [float(bar["close"]) for bar in close_bars]
    last_bar_date = date.fromisoformat(str(close_bars[-1]["date"]))
    indicators = calculate_technical_indicators(symbol, closes, as_of=last_bar_date)
    if len(hlc_bars) >= 15:
        highs = [float(bar["high"]) for bar in hlc_bars]
        lows = [float(bar["low"]) for bar in hlc_bars]
        hlc_closes = [float(bar["close"]) for bar in hlc_bars]
        atr = _wilder_atr(highs, lows, hlc_closes)
        if atr is not None:
            return indicators.model_copy(update={"atr_14": round(atr, 4)})
    return indicators


def calculate_technical_indicators(
    symbol: str,
    prices: list[float],
    *,
    as_of: date | None = None,
) -> TechnicalIndicators:
    cleaned = _validated_prices(prices, minimum=252)

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
        date=(as_of or datetime.now(timezone.utc).date()),
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
