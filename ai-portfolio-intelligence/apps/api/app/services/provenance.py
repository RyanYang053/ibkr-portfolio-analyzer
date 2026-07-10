from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from app.core.config import settings
from app.schemas.domain import Position, Provenance


@dataclass(frozen=True)
class DataSourceRecord:
    source_type: str
    provider: str
    observation_id: str | None
    observed_at: datetime | None
    as_of: date | None
    is_mock: bool
    is_cached: bool


def _normalize_provider(price_source: str | None) -> str:
    return (price_source or "broker").strip().lower()


def collect_position_source_records(positions: list[Position]) -> list[DataSourceRecord]:
    records: list[DataSourceRecord] = []
    for position in positions:
        provider = _normalize_provider(getattr(position, "price_source", None))
        is_mock = provider in {"mock", "mock_fundamentals"} or settings.broker_mode == "mock_ibkr_readonly"
        records.append(
            DataSourceRecord(
                source_type="position_price",
                provider=provider,
                observation_id=str(position.con_id) if position.con_id is not None else position.symbol,
                observed_at=getattr(position, "updated_at", None),
                as_of=None,
                is_mock=is_mock,
                is_cached=False,
            )
        )
    return records


def build_report_provenance(
    positions: list[Position],
    *,
    web_grounded: bool = False,
    cached_data: bool = False,
) -> Provenance:
    records = collect_position_source_records(positions)
    has_broker = any(record.provider in {"broker", "broker_snapshot"} for record in records)
    has_mock = any(record.is_mock for record in records)
    live_portfolio = bool(records) and has_broker and not has_mock
    if settings.broker_mode == "ibkr_readonly" and has_broker and not has_mock:
        live_portfolio = True
    mock_fallback = has_mock or settings.broker_mode == "mock_ibkr_readonly"
    return Provenance(
        live_portfolio_data=live_portfolio and not cached_data,
        live_market_data=live_portfolio and not mock_fallback and not cached_data,
        cached_data=cached_data,
        mock_fallback_data=mock_fallback,
        web_grounded_context=web_grounded,
    )
