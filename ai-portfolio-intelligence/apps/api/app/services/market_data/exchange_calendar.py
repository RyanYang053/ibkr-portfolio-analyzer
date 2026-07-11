from __future__ import annotations

from datetime import date, timedelta

# NYSE full-day closures used when exchange_calendars is unavailable.
_US_EQUITY_HOLIDAYS: set[date] = {
    date(2024, 1, 1),
    date(2024, 1, 15),
    date(2024, 2, 19),
    date(2024, 3, 29),
    date(2024, 5, 27),
    date(2024, 6, 19),
    date(2024, 7, 4),
    date(2024, 9, 2),
    date(2024, 11, 28),
    date(2024, 12, 25),
    date(2025, 1, 1),
    date(2025, 1, 20),
    date(2025, 2, 17),
    date(2025, 4, 18),
    date(2025, 5, 26),
    date(2025, 6, 19),
    date(2025, 7, 4),
    date(2025, 9, 1),
    date(2025, 11, 27),
    date(2025, 12, 25),
    date(2026, 1, 1),
    date(2026, 1, 19),
    date(2026, 2, 16),
    date(2026, 4, 3),
    date(2026, 5, 25),
    date(2026, 6, 19),
    date(2026, 7, 3),
    date(2026, 9, 7),
    date(2026, 11, 26),
    date(2026, 12, 25),
    date(2027, 1, 1),
}

_XNYS_CALENDAR = None


def _load_xnys_calendar():
    global _XNYS_CALENDAR
    if _XNYS_CALENDAR is not None:
        return _XNYS_CALENDAR
    try:
        import exchange_calendars as xcals

        _XNYS_CALENDAR = xcals.get_calendar("XNYS")
    except Exception:
        _XNYS_CALENDAR = False
    return _XNYS_CALENDAR


def is_us_equity_trading_day(day: date) -> bool:
    calendar = _load_xnys_calendar()
    if calendar:
        try:
            return bool(calendar.is_session(day.strftime("%Y-%m-%d")))
        except Exception:
            pass
    return day.weekday() < 5 and day not in _US_EQUITY_HOLIDAYS


def trading_sessions_between(start_exclusive: date, end_inclusive: date) -> int:
    """Count NYSE trading sessions in (start_exclusive, end_inclusive]."""
    if end_inclusive <= start_exclusive:
        return 0
    calendar = _load_xnys_calendar()
    if calendar:
        try:
            sessions = calendar.sessions_in_range(
                (start_exclusive + timedelta(days=1)).strftime("%Y-%m-%d"),
                end_inclusive.strftime("%Y-%m-%d"),
            )
            return len(sessions)
        except Exception:
            pass
    sessions = 0
    current = start_exclusive + timedelta(days=1)
    while current <= end_inclusive:
        if is_us_equity_trading_day(current):
            sessions += 1
        current += timedelta(days=1)
    return sessions


def previous_trading_session(day: date) -> date:
    """Return the most recent NYSE trading session strictly before ``day``."""
    current = day - timedelta(days=1)
    while not is_us_equity_trading_day(current):
        current -= timedelta(days=1)
    return current


def normalize_period_return(period_return: float, trading_sessions: int) -> float | None:
    if trading_sessions <= 0 or period_return <= -1.0 or not (period_return == period_return):
        return None
    if trading_sessions == 1:
        return period_return
    return (1.0 + period_return) ** (1.0 / trading_sessions) - 1.0
