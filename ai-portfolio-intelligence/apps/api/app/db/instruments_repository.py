"""Canonical instrument master persistence (plan §17 / §18 instruments_repository).

SQL-backed (`instruments` table) for sqlite and postgres; JSON state store fallback
for the `json` test backend so the reference layer works in every mode.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.domain.instrument import instrument_key
from app.schemas.instrument import InstrumentRecord

_NAMESPACE = "instruments"
_INDEX_KEY = "index"

_COLUMNS = (
    "instrument_id",
    "symbol",
    "con_id",
    "name",
    "asset_class",
    "currency",
    "exchange",
    "sector",
    "industry",
    "is_etf",
    "status",
    "provisional",
    "first_seen_at",
    "updated_at",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _use_sql() -> bool:
    return settings.persistence_backend in {"postgres", "sqlite"}


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _record_from_mapping(data: dict[str, Any]) -> InstrumentRecord:
    return InstrumentRecord(
        instrument_id=str(data["instrument_id"]),
        symbol=str(data["symbol"]),
        con_id=int(data["con_id"]) if data.get("con_id") is not None else None,
        name=data.get("name"),
        asset_class=data.get("asset_class"),
        currency=data.get("currency"),
        exchange=data.get("exchange"),
        sector=data.get("sector"),
        industry=data.get("industry"),
        is_etf=bool(data.get("is_etf")),
        status=str(data.get("status") or "active"),
        provisional=bool(data.get("provisional")),
        aliases=list(data.get("aliases") or []),
        first_seen_at=_parse_dt(data.get("first_seen_at")),
        updated_at=_parse_dt(data.get("updated_at")),
    )


def upsert_instrument(record: InstrumentRecord) -> InstrumentRecord:
    """Insert or update a canonical instrument. Preserves first_seen_at."""
    now = _now()
    if _use_sql():
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(
                text(
                    """
                    INSERT INTO instruments (
                        instrument_id, symbol, con_id, name, asset_class, currency,
                        exchange, sector, industry, is_etf, status, provisional,
                        first_seen_at, updated_at
                    ) VALUES (
                        :instrument_id, :symbol, :con_id, :name, :asset_class, :currency,
                        :exchange, :sector, :industry, :is_etf, :status, :provisional,
                        :now, :now
                    )
                    ON CONFLICT(instrument_id) DO UPDATE SET
                        symbol = excluded.symbol,
                        con_id = COALESCE(excluded.con_id, instruments.con_id),
                        name = COALESCE(excluded.name, instruments.name),
                        asset_class = COALESCE(excluded.asset_class, instruments.asset_class),
                        currency = COALESCE(excluded.currency, instruments.currency),
                        exchange = COALESCE(excluded.exchange, instruments.exchange),
                        sector = COALESCE(excluded.sector, instruments.sector),
                        industry = COALESCE(excluded.industry, instruments.industry),
                        is_etf = excluded.is_etf,
                        status = excluded.status,
                        provisional = excluded.provisional,
                        updated_at = excluded.updated_at
                    """
                ),
                {
                    "instrument_id": record.instrument_id,
                    "symbol": record.symbol,
                    "con_id": record.con_id,
                    "name": record.name,
                    "asset_class": record.asset_class,
                    "currency": record.currency,
                    "exchange": record.exchange,
                    "sector": record.sector,
                    "industry": record.industry,
                    "is_etf": record.is_etf,
                    "status": record.status,
                    "provisional": record.provisional,
                    "now": now,
                },
            )
            session.commit()
        stored = get_instrument(record.instrument_id)
        return stored or record

    # json backend
    from app.db.state_store import get_state_store

    store = get_state_store()
    existing = store.read_json(_NAMESPACE, record.instrument_id, default=None)
    first_seen = _parse_dt((existing or {}).get("first_seen_at")) or now
    payload = record.model_dump(mode="json")
    payload["first_seen_at"] = first_seen.isoformat()
    payload["updated_at"] = now.isoformat()
    store.write_json(_NAMESPACE, record.instrument_id, payload)
    index = store.read_json(_NAMESPACE, _INDEX_KEY, default={"ids": []}) or {"ids": []}
    ids = list(index.get("ids") or [])
    if record.instrument_id not in ids:
        ids.append(record.instrument_id)
        store.write_json(_NAMESPACE, _INDEX_KEY, {"ids": ids})
    return _record_from_mapping(payload)


def get_instrument(instrument_id: str) -> InstrumentRecord | None:
    if _use_sql():
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            row = session.execute(
                text(f"SELECT {', '.join(_COLUMNS)} FROM instruments WHERE instrument_id = :iid"),
                {"iid": instrument_id},
            ).mappings().first()
        return _record_from_mapping(dict(row)) if row else None

    from app.db.state_store import get_state_store

    data = get_state_store().read_json(_NAMESPACE, instrument_id, default=None)
    return _record_from_mapping(data) if data else None


def resolve_instrument(
    symbol: str,
    con_id: int | None = None,
    **defaults: Any,
) -> InstrumentRecord:
    """Return the canonical instrument for symbol/con_id, creating it if unseen."""
    iid = instrument_key(symbol, con_id)
    existing = get_instrument(iid)
    if existing is not None:
        return existing
    record = InstrumentRecord.build(symbol=symbol, con_id=con_id, **defaults)
    return upsert_instrument(record)


def search_instruments(query: str, *, limit: int = 25) -> list[InstrumentRecord]:
    q = (query or "").strip()
    if not q:
        return []
    like = f"{q.upper()}%"
    name_like = f"%{q}%"
    if _use_sql():
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            rows = (
                session.execute(
                    text(
                        f"""
                        SELECT {', '.join(_COLUMNS)} FROM instruments
                        WHERE UPPER(symbol) LIKE :like OR name LIKE :name_like
                        ORDER BY
                            CASE WHEN UPPER(symbol) = :exact THEN 0 ELSE 1 END,
                            symbol
                        LIMIT :limit
                        """
                    ),
                    {"like": like, "name_like": name_like, "exact": q.upper(), "limit": limit},
                )
                .mappings()
                .all()
            )
        return [_record_from_mapping(dict(r)) for r in rows]

    from app.db.state_store import get_state_store

    store = get_state_store()
    index = store.read_json(_NAMESPACE, _INDEX_KEY, default={"ids": []}) or {"ids": []}
    out: list[InstrumentRecord] = []
    for iid in index.get("ids") or []:
        data = store.read_json(_NAMESPACE, str(iid), default=None)
        if not data:
            continue
        symbol = str(data.get("symbol") or "").upper()
        name = str(data.get("name") or "")
        if symbol.startswith(q.upper()) or q.lower() in name.lower():
            out.append(_record_from_mapping(data))
    out.sort(key=lambda r: (r.symbol != q.upper(), r.symbol))
    return out[:limit]


def list_instruments(*, limit: int = 200) -> list[InstrumentRecord]:
    if _use_sql():
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            rows = (
                session.execute(
                    text(f"SELECT {', '.join(_COLUMNS)} FROM instruments ORDER BY symbol LIMIT :limit"),
                    {"limit": limit},
                )
                .mappings()
                .all()
            )
        return [_record_from_mapping(dict(r)) for r in rows]

    from app.db.state_store import get_state_store

    store = get_state_store()
    index = store.read_json(_NAMESPACE, _INDEX_KEY, default={"ids": []}) or {"ids": []}
    out = []
    for iid in (index.get("ids") or [])[:limit]:
        data = store.read_json(_NAMESPACE, str(iid), default=None)
        if data:
            out.append(_record_from_mapping(data))
    return out


def add_alias(alias: str, instrument_id: str, *, source: str = "user") -> None:
    """Register an alternate lookup token (ticker/name) for an instrument."""
    alias_norm = (alias or "").strip()
    if not alias_norm or not _use_sql():
        return
    from sqlalchemy import text

    from app.db.session import SessionLocal

    with SessionLocal() as session:
        session.execute(
            text(
                """
                INSERT INTO instrument_aliases (alias, instrument_id, source)
                VALUES (:alias, :instrument_id, :source)
                ON CONFLICT(alias, instrument_id) DO NOTHING
                """
            ),
            {"alias": alias_norm, "instrument_id": instrument_id, "source": source},
        )
        session.commit()
