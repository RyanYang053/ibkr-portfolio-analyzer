from __future__ import annotations

import time
from typing import Any

RECENCY_WINDOW_SECONDS = 14 * 24 * 60 * 60
TRUSTED_SOURCES = frozenset(
    {
        "reuters",
        "bloomberg",
        "wall street journal",
        "financial times",
        "associated press",
        "yahoo finance",
    }
)


def normalize_news_items(raw_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_titles: set[str] = set()
    normalized: list[dict[str, Any]] = []
    now = int(time.time())

    for item in raw_items:
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        dedupe_key = title.lower()
        if dedupe_key in seen_titles:
            continue
        seen_titles.add(dedupe_key)

        published_at = int(item.get("providerPublishTime") or item.get("published_at") or 0)
        if published_at > 0 and now - published_at > RECENCY_WINDOW_SECONDS:
            continue

        source = str(item.get("source") or item.get("publisher") or "unknown").strip()
        source_quality = "trusted" if source.lower() in TRUSTED_SOURCES else "experimental"
        normalized.append(
            {
                "symbol": str(item.get("symbol", "")).upper(),
                "title": title,
                "summary": str(item.get("summary", "")),
                "link": str(item.get("link", "")),
                "published_at": published_at,
                "source": source,
                "source_quality": source_quality,
            }
        )
    return normalized


def fetch_scoring_news(symbol: str, *, allow_mock: bool) -> list[dict[str, Any]]:
    from app.services.market_data.mock_provider import MockMarketDataProvider

    provider = MockMarketDataProvider(allow_mock=allow_mock)
    raw = provider.get_recent_news(symbol)
    return normalize_news_items(raw)
