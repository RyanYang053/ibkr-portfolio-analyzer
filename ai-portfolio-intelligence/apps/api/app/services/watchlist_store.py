from __future__ import annotations

from app.db.legacy_bridge import read_json_with_legacy, write_json_state
from app.services.tenant_scope import auth_scoped_defaults_enabled

_DEFAULT_WATCHLIST = [
    {
        "id": 1,
        "symbol": "AAPL",
        "reason": "Monitoring consumer hardware cyclicality and AI integration features in iOS.",
        "target_add_price": 185.00,
        "target_trim_review_price": 240.00,
        "status": "watch",
    },
    {
        "id": 2,
        "symbol": "NVDA",
        "reason": "Tracking global AI data center capital expenditures and Blackwell graphics architecture launch cadence.",
        "target_add_price": 110.00,
        "target_trim_review_price": 160.00,
        "status": "watch",
    },
    {
        "id": 3,
        "symbol": "TSLA",
        "reason": "Awaiting vehicle gross margin recovery, energy storage expansion, and FSD hardware updates.",
        "target_add_price": 165.00,
        "target_trim_review_price": 260.00,
        "status": "watch",
    },
]


def _load_watchlist_for_user(user_id: str) -> list[dict]:
    items = read_json_with_legacy("watchlist", user_id, None, default=None)
    if isinstance(items, list) and items:
        return items
    if auth_scoped_defaults_enabled():
        return []
    write_json_state("watchlist", user_id, _DEFAULT_WATCHLIST)
    return list(_DEFAULT_WATCHLIST)


def save_user_watchlist(user_id: str, items: list[dict]) -> None:
    _save_watchlist_for_user(user_id, items)


def _save_watchlist_for_user(user_id: str, items: list[dict]) -> None:
    write_json_state("watchlist", user_id, items)


def load_user_watchlist(user_id: str) -> list[dict]:
    return _load_watchlist_for_user(user_id)


def symbol_on_user_watchlist(symbol: str, user_id: str) -> bool:
    normalized = symbol.upper().strip()
    return any(item.get("symbol", "").upper() == normalized for item in _load_watchlist_for_user(user_id))
