from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

import hashlib

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.state_store import postgres_available


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def hash_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _tables_available() -> bool:
    if not postgres_available():
        return False
    try:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(text("SELECT 1 FROM sec_ticker_map_cache LIMIT 1"))
        return True
    except SQLAlchemyError:
        return False


def get_cached_ticker_map() -> dict[str, Any] | None:
    if not _tables_available():
        return None

    from app.core.config import settings
    from app.db.session import SessionLocal

    cutoff = _utc_now() - timedelta(hours=settings.sec_edgar_cache_hours)
    with SessionLocal() as session:
        row = session.execute(
            text(
                """
                SELECT payload_json
                FROM sec_ticker_map_cache
                WHERE cached_at >= :cutoff
                ORDER BY cached_at DESC
                LIMIT 1
                """
            ),
            {"cutoff": cutoff},
        ).mappings().first()
    if not row:
        return None
    return json.loads(row["payload_json"])


def cache_ticker_map(payload: dict[str, Any]) -> None:
    if not _tables_available():
        return

    from app.db.session import SessionLocal

    with SessionLocal() as session:
        session.execute(
            text(
                """
                INSERT INTO sec_ticker_map_cache (cache_key, payload_json, cached_at)
                VALUES ('company_tickers', :payload_json, :cached_at)
                ON CONFLICT ON CONSTRAINT uq_sec_ticker_map_cache_key
                DO UPDATE SET
                    payload_json = EXCLUDED.payload_json,
                    cached_at = EXCLUDED.cached_at
                """
            ),
            {"payload_json": json.dumps(payload), "cached_at": _utc_now()},
        )
        session.commit()


def get_cached_company_facts(symbol: str) -> dict[str, Any] | None:
    if not _tables_available():
        return None

    from app.core.config import settings
    from app.db.session import SessionLocal

    cutoff = _utc_now() - timedelta(hours=settings.sec_edgar_cache_hours)
    with SessionLocal() as session:
        row = session.execute(
            text(
                """
                SELECT raw_payload_json
                FROM sec_company_facts
                WHERE symbol = :symbol AND fetched_at >= :cutoff
                ORDER BY fetched_at DESC
                LIMIT 1
                """
            ),
            {"symbol": symbol.upper(), "cutoff": cutoff},
        ).mappings().first()
    if not row:
        return None
    return json.loads(row["raw_payload_json"])


def persist_company_facts(symbol: str, cik: str, payload: dict[str, Any], observations: list[dict[str, Any]]) -> None:
    if not _tables_available():
        return

    from app.db.session import SessionLocal

    source_hash = hash_payload(payload)
    entity_name = str(payload.get("entityName", ""))
    now = _utc_now()
    with SessionLocal() as session:
        session.execute(
            text(
                """
                INSERT INTO sec_company_facts (
                    symbol, cik, entity_name, source_hash, raw_payload_json, fetched_at
                ) VALUES (
                    :symbol, :cik, :entity_name, :source_hash, :raw_payload_json, :fetched_at
                )
                ON CONFLICT ON CONSTRAINT uq_sec_company_facts_symbol_hash
                DO UPDATE SET
                    entity_name = EXCLUDED.entity_name,
                    raw_payload_json = EXCLUDED.raw_payload_json,
                    fetched_at = EXCLUDED.fetched_at
                """
            ),
            {
                "symbol": symbol.upper(),
                "cik": cik,
                "entity_name": entity_name,
                "source_hash": source_hash,
                "raw_payload_json": json.dumps(payload),
                "fetched_at": now,
            },
        )
        for row in observations:
            raw_hash = hash_payload(row)
            session.execute(
                    text(
                        """
                        INSERT INTO sec_fact_observations (
                            symbol, cik, concept, unit, value, start_date, end_date,
                            filed_date, accepted_at, accn, form, fy, fp, frame,
                            source_hash, raw_hash, ingested_at
                        ) VALUES (
                            :symbol, :cik, :concept, :unit, :value, :start_date, :end_date,
                            :filed_date, :accepted_at, :accn, :form, :fy, :fp, :frame,
                            :source_hash, :raw_hash, :ingested_at
                        )
                        ON CONFLICT ON CONSTRAINT uq_sec_fact_observations_identity
                        DO UPDATE SET
                            value = EXCLUDED.value,
                            filed_date = EXCLUDED.filed_date,
                            accepted_at = EXCLUDED.accepted_at,
                            source_hash = EXCLUDED.source_hash,
                            raw_hash = EXCLUDED.raw_hash,
                            ingested_at = EXCLUDED.ingested_at
                        """
                    ),
                    {
                        "symbol": symbol.upper(),
                        "cik": cik,
                        "concept": row["concept"],
                        "unit": row["unit"],
                        "value": row["value"],
                        "start_date": _parse_date(row.get("start")),
                        "end_date": _parse_date(row.get("end")),
                        "filed_date": _parse_date(row.get("filed")),
                        "accepted_at": row.get("accepted"),
                        "accn": row.get("accn"),
                        "form": row.get("form"),
                        "fy": row.get("fy"),
                        "fp": row.get("fp"),
                        "frame": row.get("frame"),
                        "source_hash": source_hash,
                        "raw_hash": raw_hash,
                        "ingested_at": now,
                    },
                )
        session.commit()


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
