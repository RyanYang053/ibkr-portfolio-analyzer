import sys
import os
from datetime import date

# Add path so we can import app
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.services.portfolio.pnl_tracker import (
    HISTORY_FILE,
    DATA_DIR,
    get_pnl_history,
    record_pnl_snapshot,
)
from app.schemas.domain import AccountSummary, utc_now

def _make_summary(net_liq: float) -> AccountSummary:
    return AccountSummary(
        account_id="TEST",
        net_liquidation=net_liq,
        cash=32500.0,
        buying_power=125000.0,
        margin_requirement=18500.0,
        excess_liquidity=net_liq - 18500.0,
        total_unrealized_pnl=4200.0,
        total_realized_pnl=1200.0,
        base_currency="USD",
        data_timestamp=utc_now()
    )

print("HISTORY_FILE:", HISTORY_FILE)
print("DATA_DIR:", DATA_DIR)
print("is_demo:", ("pytest" in sys.modules))

# Clear any existing file
if os.path.exists(HISTORY_FILE):
    os.remove(HISTORY_FILE)

summary1 = _make_summary(150000.0)
summary2 = _make_summary(160000.0)

print("\n--- Recording snapshot 1 ---")
record_pnl_snapshot(summary1, [])

print("\n--- Recording snapshot 2 ---")
record_pnl_snapshot(summary2, [])

history = get_pnl_history()
today_entries = [h for h in history if h.date == date.today().isoformat()]
print("\n--- Results ---")
print("Total history length:", len(history))
print("Today entries length:", len(today_entries))
for idx, entry in enumerate(today_entries):
    print(f"Entry {idx}: net_liq={entry.net_liquidation}, is_mock={entry.is_mock}")
