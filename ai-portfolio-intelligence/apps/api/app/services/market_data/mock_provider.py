from __future__ import annotations

from datetime import date, timedelta
import sys
from typing import Any

from app.core.config import settings


class MockMarketDataProvider:
    def __init__(self, allow_mock: bool | None = None) -> None:
        self.allow_mock = (
            allow_mock
            if allow_mock is not None
            else settings.broker_mode == "mock_ibkr_readonly" or "pytest" in sys.modules
        )

    def get_latest_price(self, symbol: str) -> float:
        from app.services.broker.mock_ibkr import MOCK_LOTS
        if self.allow_mock and symbol.upper() in MOCK_LOTS:
            return MOCK_LOTS[symbol.upper()][2]

        import httpx
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol.upper()}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        try:
            with httpx.Client() as client:
                response = client.get(url, headers=headers, timeout=3.0)
                if response.status_code == 200:
                    price = response.json()["chart"]["result"][0]["meta"].get("regularMarketPrice")
                    if price is not None:
                        return float(price)
        except Exception as exc:
            raise RuntimeError(f"Live market price unavailable for {symbol.upper()}") from exc

        if self.allow_mock and symbol.upper() in MOCK_LOTS:
            return MOCK_LOTS[symbol.upper()][2]
        raise RuntimeError(f"Live market price unavailable for {symbol.upper()}")

    def get_historical_prices(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        total_return: bool = False,
    ) -> list[dict[str, float | str]]:
        if not self.allow_mock:
            from app.services.market_data.http_client import filter_rows_by_date, request_with_retry

            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol.upper()}?range=1y&interval=1d"
            try:
                response = request_with_retry(url, timeout=5.0)
                data = response.json()
                result = data["chart"]["result"][0]
                timestamps = result["timestamp"]
                indicators = result.get("indicators", {})
                adj = indicators.get("adjclose", [{}])[0].get("adjclose", [])
                closes = indicators.get("quote", [{}])[0].get("close", [])
                series = adj if total_return and any(value is not None for value in adj) else closes
                label = "live_yahoo_adjclose" if series is adj else "live_yahoo_finance"

                prices = []
                from datetime import datetime, timezone
                for ts, close in zip(timestamps, series):
                    if close is not None:
                        date_str = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
                        prices.append({"date": date_str, "close": float(close), "source": label})
                if prices:
                    return filter_rows_by_date(prices, start_date, end_date)
            except Exception as exc:
                raise RuntimeError(f"Live price history unavailable for {symbol.upper()}") from exc
            raise RuntimeError(f"Live price history unavailable for {symbol.upper()}")

        # Deterministic demo/test data is available only when explicitly enabled.
        from app.services.broker.mock_ibkr import MOCK_LOTS
        if symbol.upper() not in MOCK_LOTS:
            raise KeyError(f"No mock history for {symbol}")

        days = max((end_date - start_date).days, 220)
        base = MOCK_LOTS[symbol.upper()][2] * 0.72
        prices = []
        for index in range(days):
            close = base + index * (MOCK_LOTS[symbol.upper()][2] - base) / max(days - 1, 1)
            prices.append(
                {
                    "date": (start_date + timedelta(days=index)).isoformat(),
                    "close": round(close, 2),
                    "source": "mock_market_data",
                }
            )
        return prices

    def get_recent_news(self, symbol: str) -> list[dict[str, Any]]:
        if not self.allow_mock:
            import httpx
            url = f"https://query1.finance.yahoo.com/v1/finance/search?q={symbol.upper()}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            try:
                with httpx.Client() as client:
                    response = client.get(url, headers=headers, timeout=5.0)
                    if response.status_code == 200:
                        data = response.json()
                        news_items = data.get("news", [])
                        parsed_news = []
                        for item in news_items:
                            parsed_news.append({
                                "symbol": symbol.upper(),
                                "title": item.get("title", ""),
                                "summary": item.get("publisher", ""),
                                "link": item.get("link", ""),
                                "providerPublishTime": item.get("providerPublishTime", 0),
                                "source": item.get("publisher", "yahoo_finance")
                            })
                        if parsed_news:
                            return parsed_news
            except Exception as exc:
                raise RuntimeError(f"Live news unavailable for {symbol.upper()}") from exc
            raise RuntimeError(f"Live news unavailable for {symbol.upper()}")

        # Demo/test catalyst data is always labeled as mock.
        return [
            {
                "symbol": symbol.upper(),
                "title": f"Mock catalyst feed for {symbol.upper()}",
                "summary": "Live news provider returned mock fallback data.",
                "link": "https://finance.yahoo.com",
                "providerPublishTime": 0,
                "source": "mock_news",
            }
        ]

    def get_chart_data(self, symbol: str, range_str: str = "1y", interval_str: str = "1d") -> list[dict[str, float | str]]:
        if not self.allow_mock:
            import httpx
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol.upper()}?range={range_str}&interval={interval_str}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            try:
                with httpx.Client() as client:
                    response = client.get(url, headers=headers, timeout=5.0)
                    if response.status_code == 200:
                        data = response.json()
                        result = data["chart"]["result"][0]
                        timestamps = result.get("timestamp", [])
                        indicators = result.get("indicators", {})
                        quote = indicators.get("quote", [{}])[0]
                        closes = quote.get("close", [])
                        opens = quote.get("open", [])
                        highs = quote.get("high", [])
                        lows = quote.get("low", [])
                        
                        prices = []
                        from datetime import datetime, timezone
                        for ts, close, open_p, high, low in zip(timestamps, closes, opens, highs, lows):
                            if None not in (close, open_p, high, low):
                                date_str = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                                prices.append({
                                    "date": date_str,
                                    "close": float(close),
                                    "open": float(open_p),
                                    "high": float(high),
                                    "low": float(low),
                                    "source": "live_yahoo_finance",
                                })
                        if prices:
                            return prices
            except Exception as exc:
                raise RuntimeError(f"Live chart data unavailable for {symbol.upper()}") from exc
            raise RuntimeError(f"Live chart data unavailable for {symbol.upper()}")

        # Deterministic demo/test chart data.
        from app.services.broker.mock_ibkr import MOCK_LOTS
        base_price = 100.0
        if symbol.upper() in MOCK_LOTS:
            base_price = MOCK_LOTS[symbol.upper()][2]
        
        # Determine number of items based on range
        items_count = 24 if range_str == "1d" else 30 if range_str == "1mo" else 90 if range_str == "3mo" else 260
        prices = []
        import math
        from datetime import date, datetime, time, timedelta, timezone
        end_date = date.today()
        for i in range(items_count):
            if range_str == "1d":
                start_time = datetime.combine(end_date, time(13, 30), tzinfo=timezone.utc)
                delta = timedelta(hours=6.5)  # 9:30 AM to 4:00 PM EST (6.5 hours)
                divisor = max(1, items_count - 1)
                dt = (start_time + delta * (i / divisor)).isoformat()
            else:
                dt = (end_date - timedelta(days=items_count - 1 - i)).isoformat()
            factor = 1.0 + 0.05 * math.sin(i / 10.0) + (i / items_count) * 0.15
            close = base_price * factor
            prices.append({
                "date": dt,
                "close": round(close, 2),
                "open": round(close * 0.99, 2),
                "high": round(close * 1.01, 2),
                "low": round(close * 0.985, 2),
                "source": "mock_market_data",
            })
        return prices


