from __future__ import annotations

from typing import Any

from app.db.legacy_bridge import read_json_with_legacy, write_json_state
from app.services.tenant_scope import scoped_record_key

REPORTS_FILE = __import__("os").path.join(
    __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.dirname(__file__)))),
    "ai_reports.json",
)


def _load_reports() -> dict[str, dict[str, Any]]:
    data = read_json_with_legacy("ai_reports", "cache", REPORTS_FILE if __import__("os").path.exists(REPORTS_FILE) else None, default={})
    return data if isinstance(data, dict) else {}


_ai_reports_cache: dict[str, dict[str, Any]] = _load_reports()


def _save_reports() -> None:
    write_json_state("ai_reports", "cache", _ai_reports_cache)
    try:
        import json

        with open(REPORTS_FILE, "w", encoding="utf-8") as f:
            json.dump(_ai_reports_cache, f, indent=2)
    except Exception:
        pass


def _scoped_key(user_id: str, account_id: str, symbol: str, *, report_type: str = "stock") -> str:
    return scoped_record_key(user_id, account_id, symbol.upper(), report_type)


def get_cached_report(
    symbol: str,
    *,
    user_id: str,
    account_id: str,
    report_type: str = "stock",
) -> dict[str, Any] | None:
    key = _scoped_key(user_id, account_id, symbol, report_type=report_type)
    return _ai_reports_cache.get(key)


def set_cached_report(
    symbol: str,
    report: dict[str, Any],
    *,
    user_id: str,
    account_id: str,
    report_type: str = "stock",
) -> None:
    key = _scoped_key(user_id, account_id, symbol, report_type=report_type)
    _ai_reports_cache[key] = report
    _save_reports()
