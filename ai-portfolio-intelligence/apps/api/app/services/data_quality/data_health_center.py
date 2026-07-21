"""Data Health Center aggregation service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

_VALUATION_METHODOLOGY_IDS = (
    "general_operating_dcf",
    "bank_residual_income",
    "reit_nav_affo",
    "utility_rate_base",
)


def _valuation_health_check() -> dict[str, Any]:
    try:
        from app.db.methodology_repo import load_methodology_registry

        records = {
            item.methodology_id: item.approval_status
            for item in load_methodology_registry()
            if item.methodology_id in _VALUATION_METHODOLOGY_IDS
        }
    except Exception:
        records = {}
    if not records:
        return {
            "id": "valuation",
            "status": "withheld",
            "detail": "Primary valuation models remain withheld pending fixtures",
        }
    approved = [
        mid
        for mid, status in records.items()
        if status in {"approved", "approved_for_personal_use"}
    ]
    withheld = [mid for mid, status in records.items() if status == "withheld"]
    if len(approved) == len(_VALUATION_METHODOLOGY_IDS):
        return {
            "id": "valuation",
            "status": "approved_for_personal_use",
            "detail": "Valuation models approved_for_personal_use with golden fixtures",
        }
    if approved:
        return {
            "id": "valuation",
            "status": "provisional",
            "detail": f"{len(approved)}/{len(_VALUATION_METHODOLOGY_IDS)} valuation models approved",
        }
    if withheld:
        return {
            "id": "valuation",
            "status": "withheld",
            "detail": "Primary valuation models remain withheld pending fixtures",
        }
    return {
        "id": "valuation",
        "status": "experimental",
        "detail": "Valuation models present but not yet approved_for_personal_use",
    }


def _tax_lots_health_check() -> dict[str, Any]:
    try:
        from app.db.methodology_repo import load_methodology_registry

        record = next(
            (
                item
                for item in load_methodology_registry()
                if item.methodology_id == "tax_lot_methodology"
            ),
            None,
        )
    except Exception:
        record = None
    if record is None:
        return {
            "id": "tax_lots",
            "status": "experimental",
            "detail": "Tax outputs are decision-support estimates unless broker-reconciled",
        }
    if record.approval_status in {"approved", "approved_for_personal_use"}:
        return {
            "id": "tax_lots",
            "status": "approved_for_personal_use",
            "detail": "Tax lot methodology approved_for_personal_use; filing worksheets still need professional review",
        }
    return {
        "id": "tax_lots",
        "status": record.approval_status,
        "detail": "Tax outputs are decision-support estimates unless broker-reconciled",
    }


def build_data_health_report(
    *,
    account_id: str | None = None,
    broker_status: dict[str, Any] | None = None,
    schedule_runs: list[dict[str, Any]] | None = None,
    methodology_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    broker = broker_status or {}
    runs = schedule_runs or []
    failed_jobs = [r for r in runs if str(r.get("status") or "").lower() in {"failed", "error"}]
    last_success = next(
        (r for r in runs if str(r.get("status") or "").lower() in {"completed", "success"}),
        None,
    )

    checks = [
        {
            "id": "broker_sync",
            "status": "available" if broker.get("connected") else "incomplete",
            "detail": broker.get("message") or broker.get("status") or "unknown",
        },
        {
            "id": "flex_sync",
            "status": "available" if broker.get("flex_configured") else "provisional",
            "detail": "Flex token configured" if broker.get("flex_configured") else "Flex not configured",
        },
        {
            "id": "scheduled_jobs",
            "status": "failed" if failed_jobs else ("available" if last_success else "incomplete"),
            "detail": f"{len(failed_jobs)} failed / {len(runs)} recent runs",
        },
        {
            "id": "methodology_approval",
            "status": (methodology_summary or {}).get("overall_status") or "experimental",
            "detail": (methodology_summary or {}).get("note")
            or "No methodology is approved_for_personal_use yet",
        },
        _valuation_health_check(),
        _tax_lots_health_check(),
        {
            "id": "backup",
            "status": "provisional",
            "detail": (
                "Create backups from Settings. Weekly zip backups run on desktop when the "
                "scheduler is enabled; passphrase encryption and verify-restore are manual."
            ),
        },
    ]

    critical = [c for c in checks if c["status"] in {"failed", "incomplete", "withheld"}]
    return {
        "account_id": account_id,
        "as_of": now.isoformat(),
        "overall_status": "attention_required" if critical else "ok",
        "checks": checks,
        "separations": [
            "available",
            "provisional",
            "experimental",
            "incomplete",
            "stale",
            "withheld",
            "failed",
        ],
        "note": "Missing fields never silently become zero.",
        "order_generated": False,
    }
