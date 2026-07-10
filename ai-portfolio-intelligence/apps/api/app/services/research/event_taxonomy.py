from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

EventCategory = Literal[
    "earnings",
    "guidance",
    "dividend",
    "split",
    "merger",
    "regulatory",
    "macro",
    "analyst_revision",
    "management_change",
    "product_launch",
    "litigation",
    "other",
]

EventSentiment = Literal["positive", "negative", "neutral", "mixed", "unknown"]


class ResearchEvent(BaseModel):
    event_id: str
    symbol: str | None = None
    category: EventCategory
    headline: str
    summary: str = ""
    sentiment: EventSentiment = "unknown"
    source: str
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    feature_tags: list[str] = Field(default_factory=list)


def classify_news_event(headline: str, summary: str = "") -> ResearchEvent:
    text = f"{headline} {summary}".lower()
    category: EventCategory = "other"
    sentiment: EventSentiment = "neutral"
    tags: list[str] = []

    if any(token in text for token in ("earnings", "eps", "quarter", "results")):
        category = "earnings"
    elif any(token in text for token in ("guidance", "outlook", "forecast")):
        category = "guidance"
    elif "dividend" in text:
        category = "dividend"
    elif any(token in text for token in ("split", "stock split")):
        category = "split"
    elif any(token in text for token in ("merger", "acquisition", "acquire")):
        category = "merger"
    elif any(token in text for token in ("sec", "fda", "regulator", "investigation")):
        category = "regulatory"
    elif any(token in text for token in ("fed", "cpi", "inflation", "rates", "jobs report")):
        category = "macro"
    elif any(token in text for token in ("upgrade", "downgrade", "price target", "analyst")):
        category = "analyst_revision"
    elif any(token in text for token in ("ceo", "cfo", "resign", "appoint")):
        category = "management_change"
    elif any(token in text for token in ("launch", "product", "release")):
        category = "product_launch"
    elif any(token in text for token in ("lawsuit", "litigation", "settlement")):
        category = "litigation"

    if any(token in text for token in ("beat", "surge", "record", "strong", "upgrade", "raised")):
        sentiment = "positive"
    elif any(token in text for token in ("miss", "cut", "weak", "downgrade", "probe", "lawsuit")):
        sentiment = "negative"
    elif category == "macro":
        sentiment = "mixed"

    if "finbert" in text:
        tags.append("finbert_feature_pending")

    return ResearchEvent(
        event_id=f"evt-{abs(hash(headline)) % 10_000_000}",
        category=category,
        headline=headline.strip(),
        summary=summary.strip(),
        sentiment=sentiment,
        source="news_classifier",
        feature_tags=tags,
    )
