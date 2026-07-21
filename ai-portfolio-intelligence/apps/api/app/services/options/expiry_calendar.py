"""Options expiry calendar and lifecycle alerts (fail-closed for unsupported models)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any


def _american_approved() -> bool:
    try:
        from app.db.methodology_repo import load_methodology_registry

        record = next(
            (
                item
                for item in load_methodology_registry()
                if item.methodology_id == "options_american_pricer"
            ),
            None,
        )
        return bool(record and record.approval_status in {"approved", "approved_for_personal_use"})
    except Exception:
        return False


def _regt_approved() -> bool:
    try:
        from app.db.methodology_repo import load_methodology_registry

        record = next(
            (
                item
                for item in load_methodology_registry()
                if item.methodology_id == "options_margin_regt"
            ),
            None,
        )
        return bool(record and record.approval_status in {"approved", "approved_for_personal_use"})
    except Exception:
        return False


def build_options_expiry_calendar(
    positions: list[dict[str, Any]],
    *,
    as_of: date | None = None,
) -> dict[str, Any]:
    today = as_of or datetime.now(timezone.utc).date()
    american_ok = _american_approved()
    regt_ok = _regt_approved()
    events: list[dict[str, Any]] = []
    for pos in positions:
        asset_class = str(pos.get("asset_class") or "")
        if asset_class not in {"OPT", "FOP"}:
            continue
        expiry_raw = pos.get("expiry") or pos.get("lastTradeDateOrContractMonth")
        expiry: date | None = None
        if isinstance(expiry_raw, date):
            expiry = expiry_raw
        elif expiry_raw:
            try:
                text = str(expiry_raw).replace("-", "")[:8]
                expiry = date(int(text[0:4]), int(text[4:6]), int(text[6:8]))
            except Exception:
                expiry = None
        if expiry is None:
            events.append(
                {
                    "symbol": pos.get("symbol"),
                    "status": "incomplete",
                    "blocker": "missing_expiry",
                    "dte": None,
                }
            )
            continue
        dte = (expiry - today).days
        severity = "routine"
        if dte <= 7:
            severity = "urgent"
        elif dte <= 21:
            severity = "this_week"

        regt_estimate = None
        if regt_ok and float(pos.get("quantity") or 0) < 0:
            try:
                from app.services.options.regt_margin import estimate_regt_margin

                underlying = float(pos.get("underlying_price") or pos.get("spot") or 0)
                strike = float(pos.get("strike") or 0)
                mult = float(pos.get("multiplier") or 100)
                shares = abs(float(pos.get("quantity") or 0)) * mult
                premium = float(pos.get("market_price") or 0) * shares
                right = str(pos.get("right") or pos.get("option_right") or "P").upper()
                strategy = "short_put_uncovered" if right.startswith("P") else "short_call_uncovered"
                if underlying > 0 and strike > 0 and shares > 0:
                    regt_estimate = estimate_regt_margin(
                        strategy=strategy,  # type: ignore[arg-type]
                        underlying_price=underlying,
                        strike=strike,
                        shares=shares,
                        premium=premium,
                    ).as_dict()
            except Exception:
                regt_estimate = None

        events.append(
            {
                "symbol": pos.get("symbol"),
                "instrument_key": pos.get("instrument_key") or pos.get("symbol"),
                "expiry": expiry.isoformat(),
                "dte": dte,
                "priority": severity,
                "assignment_probability": "withheld",
                "american_exercise": (
                    "available_crr" if american_ok else "withheld_unsupported"
                ),
                "portfolio_margin": "withheld_broker_equivalent",
                "regt_margin": regt_estimate,
                "status": "available",
            }
        )
    events.sort(key=lambda e: (e.get("dte") is None, e.get("dte") if e.get("dte") is not None else 10**9))
    return {
        "as_of": today.isoformat(),
        "events": events,
        "count": len(events),
        "methodology_status": (
            "approved_for_personal_use" if (american_ok or regt_ok) else "experimental"
        ),
        "order_generated": False,
        "note": (
            "American CRR and Reg T worksheets available when methodologies are "
            "approved_for_personal_use. IBKR Portfolio Margin (TIMS) may differ."
        ),
    }
