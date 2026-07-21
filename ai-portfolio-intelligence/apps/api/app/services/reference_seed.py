"""Seed the instrument master from the vendored FinanceDatabase reference data.

FinanceDatabase (JerBouma/FinanceDatabase, MIT) publishes symbol metadata with
cross-identifiers (ISIN/CUSIP/FIGI). A bounded, authentic slice is vendored under
``app/data/reference/financedatabase/`` (large/mega-cap equities + USD ETFs, with the
bulky ``summary`` column dropped) so seeding is fully offline — the FinanceDatabase pip
package is deliberately NOT used because it fetches from GitHub at import time.

Run: ``python -m app.services.reference_seed`` (idempotent upserts). The row→record
mapping is pure and unit-tested; the seed loop is a thin wrapper over the repository.
"""

from __future__ import annotations

import bz2
import csv
from pathlib import Path
from typing import IO, Iterable

from app.db.instruments_repository import add_alias, upsert_instrument
from app.schemas.instrument import InstrumentRecord

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "reference" / "financedatabase"
_ALIAS_SOURCE = "financedatabase"


def row_to_record(row: dict[str, str], *, is_etf: bool) -> InstrumentRecord:
    """Map one FinanceDatabase CSV row to a canonical InstrumentRecord."""
    if is_etf:
        return InstrumentRecord.build(
            symbol=row["symbol"],
            name=(row.get("name") or None),
            asset_class="ETF",
            is_etf=True,
            currency=(row.get("currency") or None),
            exchange=(row.get("exchange") or row.get("mic") or None),
            sector=(row.get("category_group") or None),
            industry=(row.get("category") or None),
        )
    return InstrumentRecord.build(
        symbol=row["symbol"],
        name=(row.get("name") or None),
        asset_class="STK",
        is_etf=False,
        currency=(row.get("currency") or None),
        exchange=(row.get("exchange") or row.get("mic") or None),
        sector=(row.get("sector") or None),
        industry=(row.get("industry") or None),
    )


def alias_tokens(row: dict[str, str]) -> list[str]:
    """Extract the cross-identifier aliases (ISIN/CUSIP/FIGI) present on a row."""
    symbol = (row.get("symbol") or "").strip().upper()
    seen: set[str] = set()
    tokens: list[str] = []
    for key in ("isin", "cusip", "figi", "composite_figi"):
        value = (row.get(key) or "").strip()
        if value and value.upper() != symbol and value not in seen:
            seen.add(value)
            tokens.append(value)
    return tokens


def _open(path: Path) -> IO[str]:
    if path.suffix == ".bz2":
        return bz2.open(path, "rt", encoding="utf-8", errors="replace")
    return open(path, encoding="utf-8", errors="replace")


def _rows(path: Path) -> Iterable[dict[str, str]]:
    with _open(path) as handle:
        yield from csv.DictReader(handle)


def seed_file(path: Path, *, is_etf: bool, limit: int | None = None) -> tuple[int, int]:
    """Upsert every instrument in ``path``; returns (instruments, aliases) counts."""
    instruments = 0
    aliases = 0
    for index, row in enumerate(_rows(path)):
        if limit is not None and index >= limit:
            break
        if not (row.get("symbol") or "").strip():
            continue
        record = row_to_record(row, is_etf=is_etf)
        upsert_instrument(record)
        instruments += 1
        for token in alias_tokens(row):
            add_alias(token, record.instrument_id, source=_ALIAS_SOURCE)
            aliases += 1
    return instruments, aliases


def seed_all(*, data_dir: Path = DATA_DIR, limit: int | None = None) -> dict[str, tuple[int, int]]:
    """Seed both vendored files. Missing files are skipped (returns zero counts)."""
    results: dict[str, tuple[int, int]] = {}
    for name, is_etf in (("equities_reference.csv", False), ("etfs_reference.csv", True)):
        path = data_dir / name
        results[name] = seed_file(path, is_etf=is_etf, limit=limit) if path.exists() else (0, 0)
    return results


if __name__ == "__main__":  # pragma: no cover - operational entry point
    summary = seed_all()
    for filename, (instruments, aliases) in summary.items():
        print(f"{filename}: {instruments} instruments, {aliases} aliases")
