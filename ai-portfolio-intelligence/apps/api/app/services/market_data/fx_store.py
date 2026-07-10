from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import date, datetime, timedelta, timezone
from threading import Lock
from typing import Optional

from app.services.market_data.http_client import request_with_retry

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
FX_STORE_FILE = os.path.join(DATA_DIR, "historical_fx_rates.json")
_FILE_LOCK = Lock()
_MEMORY_CACHE: dict[str, dict[str, float]] = {}


def _pair_key(from_curr: str, to_curr: str) -> str:
    return f"{from_curr.upper()}_{to_curr.upper()}"


def _yahoo_pair_symbol(from_curr: str, to_curr: str) -> str:
    return f"{from_curr.upper()}{to_curr.upper()}=X"


def _load_store() -> dict[str, dict[str, float]]:
    if not os.path.exists(FX_STORE_FILE):
        return {}
    with _FILE_LOCK, open(FX_STORE_FILE, "r", encoding="utf-8") as handle:
        raw = json.load(handle)
    return raw if isinstance(raw, dict) else {}


def _save_store(store: dict[str, dict[str, float]]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with _FILE_LOCK:
        fd, temporary_path = tempfile.mkstemp(prefix="fx_rates_", suffix=".tmp", dir=DATA_DIR)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(store, handle, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, FX_STORE_FILE)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)


def _fetch_yahoo_fx_series(from_curr: str, to_curr: str, start_date: date, end_date: date) -> dict[str, float]:
    period1 = int(datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc).timestamp())
    period2 = int(datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc).timestamp())
    symbol = _yahoo_pair_symbol(from_curr, to_curr)
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?period1={period1}&period2={period2}&interval=1d"
    )
    response = request_with_retry(url, timeout=6.0, max_attempts=3)
    payload = response.json()
    result = payload.get("chart", {}).get("result") or []
    if not result:
        raise RuntimeError(f"No FX history for {from_curr}/{to_curr}")
    timestamps = result[0].get("timestamp") or []
    closes = (result[0].get("indicators", {}).get("quote") or [{}])[0].get("close") or []
    series: dict[str, float] = {}
    for timestamp, close in zip(timestamps, closes):
        if close is None or not math.isfinite(float(close)) or float(close) <= 0:
            continue
        day = datetime.fromtimestamp(int(timestamp), tz=timezone.utc).date().isoformat()
        series[day] = float(close)
    if not series:
        raise RuntimeError(f"Empty FX history for {from_curr}/{to_curr}")
    return series


def _merge_series_into_store(pair: str, series: dict[str, float]) -> None:
    store = _load_store()
    existing = store.get(pair, {})
    existing.update(series)
    store[pair] = dict(sorted(existing.items()))
    _save_store(store)
    _MEMORY_CACHE[pair] = store[pair]


def _lookup_rate(series: dict[str, float], as_of: date) -> Optional[float]:
    if not series:
        return None
    as_of_text = as_of.isoformat()
    if as_of_text in series:
        return series[as_of_text]
    prior_dates = [day for day in series if day <= as_of_text]
    if prior_dates:
        return series[sorted(prior_dates)[-1]]
    return None


def get_historical_exchange_rate(from_curr: str, to_curr: str, as_of: date) -> float:
    """Return the FX rate to convert ``from_curr`` amounts into ``to_curr`` on ``as_of``."""
    native = (from_curr or "USD").upper()
    reporting = (to_curr or "USD").upper()
    if native == reporting:
        return 1.0

    pair = _pair_key(native, reporting)
    if pair not in _MEMORY_CACHE:
        _MEMORY_CACHE.update(_load_store())

    series = _MEMORY_CACHE.get(pair, {})
    rate = _lookup_rate(series, as_of)
    if rate is not None:
        return rate

    inverse_pair = _pair_key(reporting, native)
    inverse_series = _MEMORY_CACHE.get(inverse_pair, _load_store().get(inverse_pair, {}))
    inverse_rate = _lookup_rate(inverse_series, as_of)
    if inverse_rate is not None and inverse_rate > 0:
        return 1.0 / inverse_rate

    start_date = as_of - timedelta(days=14)
    fetched = _fetch_yahoo_fx_series(native, reporting, start_date, as_of)
    _merge_series_into_store(pair, fetched)
    rate = _lookup_rate(fetched, as_of)
    if rate is None:
        raise RuntimeError(f"Historical FX unavailable for {native}/{reporting} on {as_of.isoformat()}")
    return rate


def make_transaction_fx_resolver():
    from app.services.broker.ibkr_readonly import get_exchange_rate

    def resolver(from_curr: str, to_curr: str, trade_date: date | None = None) -> float:
        if trade_date is None:
            return get_exchange_rate(from_curr, to_curr)
        return get_historical_exchange_rate(from_curr, to_curr, trade_date)

    return resolver
