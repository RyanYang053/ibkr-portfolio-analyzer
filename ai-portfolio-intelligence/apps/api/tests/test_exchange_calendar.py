from datetime import date

from app.services.market_data.exchange_calendar import (
    is_us_equity_trading_day,
    normalize_period_return,
    trading_sessions_between,
)


def test_trading_sessions_skip_weekends():
    start = date(2026, 7, 10)  # Friday
    end = date(2026, 7, 13)  # Monday
    assert trading_sessions_between(start, end) == 1


def test_normalize_period_return_scales_multi_day_interval():
    daily_equiv = normalize_period_return(0.02, 2)
    assert daily_equiv is not None
    assert daily_equiv < 0.02


def test_us_holiday_is_not_trading_day():
    assert is_us_equity_trading_day(date(2026, 7, 4)) is False
