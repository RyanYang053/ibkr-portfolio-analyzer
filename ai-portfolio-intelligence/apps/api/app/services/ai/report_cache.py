from __future__ import annotations

from typing import Any

from app.db.legacy_bridge import read_json_with_legacy, write_json_state

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


def get_cached_report(symbol: str) -> dict[str, Any] | None:
    return _ai_reports_cache.get(symbol.upper().strip())


def set_cached_report(symbol: str, report: dict[str, Any]) -> None:
    _ai_reports_cache[symbol.upper().strip()] = report
    _save_reports()
