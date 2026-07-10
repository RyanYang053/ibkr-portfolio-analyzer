from app.services.market_data.news_service import normalize_news_items


def test_normalize_news_deduplicates_and_flags_source_quality(monkeypatch):
    import time

    now = int(time.time())
    items = normalize_news_items(
        [
            {
                "symbol": "AAPL",
                "title": "Apple beats estimates",
                "summary": "Reuters",
                "link": "https://example.com/1",
                "providerPublishTime": now,
                "source": "Reuters",
            },
            {
                "symbol": "AAPL",
                "title": "Apple beats estimates",
                "summary": "duplicate",
                "link": "https://example.com/2",
                "providerPublishTime": now,
                "source": "Blog",
            },
        ]
    )
    assert len(items) == 1
    assert items[0]["source_quality"] == "trusted"


def test_normalize_news_excludes_stale_items():
    items = normalize_news_items(
        [
            {
                "symbol": "MSFT",
                "title": "Old headline",
                "summary": "",
                "link": "",
                "providerPublishTime": 1,
                "source": "Yahoo Finance",
            }
        ]
    )
    assert items == []
