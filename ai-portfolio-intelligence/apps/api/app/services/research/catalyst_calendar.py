"""Catalyst calendar for research prioritization."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any


def build_catalyst_calendar(
    symbols: list[str],
    *,
    as_of: date | None = None,
    option_positions: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build catalyst events from options expiry, news when available, else provisional windows."""
    today = as_of or date.today()
    events: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for position in option_positions or []:
        symbol = str(position.get("symbol") or "").upper()
        expiry = position.get("expiry") or position.get("lastTradeDateOrContractMonth")
        if not symbol or not expiry:
            continue
        try:
            event_date = date.fromisoformat(str(expiry)[:10])
        except ValueError:
            # IBKR month format YYYYMM
            raw = str(expiry).replace("-", "")[:8]
            if len(raw) >= 6 and raw.isdigit():
                try:
                    event_date = date(int(raw[:4]), int(raw[4:6]), 15)
                except ValueError:
                    continue
            else:
                continue
        key = (symbol, "option_expiry", event_date.isoformat())
        if key in seen:
            continue
        seen.add(key)
        events.append(
            {
                "symbol": symbol,
                "catalyst_type": "option_expiry",
                "event_date": event_date.isoformat(),
                "confidence": "available",
                "source": "option_position_expiry",
                "notes": "Derived from held option contract expiry.",
                "dte": (event_date - today).days,
            }
        )

    for idx, symbol in enumerate(symbols):
        sym = symbol.upper()
        news_events = _news_catalysts(sym, today)
        if news_events:
            for item in news_events:
                key = (sym, str(item.get("catalyst_type")), str(item.get("event_date")))
                if key in seen:
                    continue
                seen.add(key)
                events.append(item)
            continue
        # Provisional window only when no real catalyst evidence exists.
        event_date = today + timedelta(days=14 + (idx % 10))
        key = (sym, "earnings_window", event_date.isoformat())
        if key in seen:
            continue
        seen.add(key)
        events.append(
            {
                "symbol": sym,
                "catalyst_type": "earnings_window",
                "event_date": event_date.isoformat(),
                "confidence": "provisional",
                "source": "provisional_calendar",
                "notes": "No provider earnings date; provisional research window only.",
                "methodology_status": "experimental",
            }
        )

    events.sort(key=lambda e: str(e.get("event_date") or ""))
    return events


def _news_catalysts(symbol: str, today: date) -> list[dict[str, Any]]:
    try:
        import sys

        from app.core.config import settings
        from app.services.market_data.mock_provider import MockMarketDataProvider

        allow_mock = settings.broker_mode == "mock_ibkr_readonly" or "pytest" in sys.modules
        news = MockMarketDataProvider(allow_mock=allow_mock).get_recent_news(symbol)
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for item in (news or [])[:3]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("headline") or "").strip()
        if not title:
            continue
        published = item.get("published_at") or item.get("date") or today.isoformat()
        try:
            event_date = date.fromisoformat(str(published)[:10])
        except ValueError:
            event_date = today
        out.append(
            {
                "symbol": symbol,
                "catalyst_type": "news_item",
                "event_date": event_date.isoformat(),
                "confidence": "provisional",
                "source": str(item.get("source") or "news_feed"),
                "notes": title[:200],
                "methodology_status": "experimental",
            }
        )
    return out


def days_until_next_catalyst(events: list[dict[str, Any]], symbol: str, *, as_of: date | None = None) -> int | None:
    today = as_of or date.today()
    upcoming = []
    for event in events:
        if event.get("symbol") != symbol:
            continue
        try:
            event_date = date.fromisoformat(str(event["event_date"]))
        except (KeyError, ValueError):
            continue
        delta = (event_date - today).days
        if delta >= 0:
            upcoming.append(delta)
    return min(upcoming) if upcoming else None
