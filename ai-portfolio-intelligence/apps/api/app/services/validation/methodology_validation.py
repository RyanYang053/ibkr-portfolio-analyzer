"""Methodology validation helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.product_contract import MethodologyStatus
from app.db.state_store import get_state_store

_NAMESPACE = "methodology_approvals"


def list_methodologies() -> list[dict[str, Any]]:
    store = get_state_store()
    index = store.read_json(_NAMESPACE, "catalog", default={"items": []}) or {}
    items = list(index.get("items") or [])
    if not items:
        # Prefer live methodology registry when available.
        try:
            from app.services.methodology_registry import DEFAULT_METHODOLOGIES

            registry_items = []
            for item in DEFAULT_METHODOLOGIES:
                registry_items.append(
                    {
                        "methodology_id": getattr(item, "methodology_id", None)
                        or (item.get("methodology_id") if isinstance(item, dict) else None),
                        "name": getattr(item, "name", None)
                        or (item.get("name") if isinstance(item, dict) else None)
                        or getattr(item, "methodology_id", None),
                        "status": getattr(item, "approval_status", None)
                        or (item.get("approval_status") if isinstance(item, dict) else None)
                        or MethodologyStatus.EXPERIMENTAL.value,
                        "version": getattr(item, "version", None)
                        or (item.get("version") if isinstance(item, dict) else None)
                        or "0.0.0",
                        "independent_validation_fixture": getattr(
                            item, "independent_validation_fixture", None
                        ),
                        "known_limitations": list(getattr(item, "known_limitations", ()) or ()),
                    }
                )
            if registry_items:
                items = registry_items
        except Exception:
            pass
    if not items:
        items = [
            {
                "methodology_id": "decision_center_holding",
                "name": "Holding Decision Center",
                "status": MethodologyStatus.EXPERIMENTAL.value,
                "version": "2.0.0",
            },
            {
                "methodology_id": "general_operating_dcf",
                "name": "General operating company DCF",
                "status": MethodologyStatus.WITHHELD.value,
                "version": "0.1.0",
            },
            {
                "methodology_id": "portfolio_construction_scenarios",
                "name": "Portfolio Construction Scenarios",
                "status": MethodologyStatus.EXPERIMENTAL.value,
                "version": "1.0.0",
            },
            {
                "methodology_id": "planning_policy_builder",
                "name": "Planning Policy Builder",
                "status": MethodologyStatus.EXPERIMENTAL.value,
                "version": "1.0.0",
            },
        ]

    approvals = store.read_json(_NAMESPACE, "approvals", default={"keys": []}) or {}
    approved_keys = {str(k) for k in list(approvals.get("keys") or [])}
    merged: list[dict[str, Any]] = []
    for item in items:
        row = dict(item)
        mid = str(row.get("methodology_id") or "")
        version = str(row.get("version") or "0.0.0")
        if f"{mid}:{version}" in approved_keys or any(k.startswith(f"{mid}:") for k in approved_keys):
            row["status"] = MethodologyStatus.APPROVED_FOR_PERSONAL_USE.value
        merged.append(row)
    return merged


def record_approval(
    *,
    methodology_id: str,
    version: str,
    approver: str,
    notes: str | None = None,
) -> dict[str, Any]:
    row = {
        "methodology_id": methodology_id,
        "version": version,
        "approver": approver,
        "notes": notes,
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "status": MethodologyStatus.APPROVED_FOR_PERSONAL_USE.value,
    }
    store = get_state_store()
    key = f"{methodology_id}:{version}"
    store.write_json(_NAMESPACE, key, row)
    index = store.read_json(_NAMESPACE, "approvals", default={"keys": []}) or {}
    keys = list(index.get("keys") or [])
    if key not in keys:
        keys.insert(0, key)
    store.write_json(_NAMESPACE, "approvals", {"keys": keys})
    # Keep catalog in sync for list views.
    catalog = store.read_json(_NAMESPACE, "catalog", default={"items": []}) or {}
    items = list(catalog.get("items") or list_methodologies())
    updated = False
    for item in items:
        if str(item.get("methodology_id")) == methodology_id:
            item["status"] = MethodologyStatus.APPROVED_FOR_PERSONAL_USE.value
            item["version"] = version
            updated = True
    if not updated:
        items.append(
            {
                "methodology_id": methodology_id,
                "name": methodology_id,
                "status": MethodologyStatus.APPROVED_FOR_PERSONAL_USE.value,
                "version": version,
            }
        )
    store.write_json(_NAMESPACE, "catalog", {"items": items})
    # Dual-write SQL tables when present (0032 / 0034).
    try:
        from app.db.methodology_approval_repo import (
            write_personal_methodology_approval,
            write_valuation_model_approval,
        )

        approved_at = datetime.fromisoformat(row["approved_at"].replace("Z", "+00:00"))
        write_personal_methodology_approval(
            methodology_id=methodology_id,
            version=version,
            approver=approver,
            status=row["status"],
            notes=notes,
            approved_at=approved_at,
            payload=row,
        )
        if methodology_id in {
            "general_operating_dcf",
            "bank_residual_income",
            "reit_nav_affo",
            "utility_rate_base",
            "scenario_fair_value",
        }:
            write_valuation_model_approval(
                model_id=methodology_id,
                version=version,
                status=row["status"],
                approver=approver,
                approved_at=approved_at,
                payload=row,
            )
    except Exception:
        pass
    return row


def validate_methodology_claim(methodology_id: str, claimed_status: str) -> dict[str, Any]:
    catalog = {m["methodology_id"]: m for m in list_methodologies()}
    current = catalog.get(methodology_id)
    if current is None:
        return {
            "ok": False,
            "methodology_id": methodology_id,
            "reason": "unknown_methodology",
            "claimed_status": claimed_status,
        }
    allowed = {
        MethodologyStatus.WITHHELD.value,
        MethodologyStatus.EXPERIMENTAL.value,
        MethodologyStatus.INTERNALLY_VALIDATED.value,
        MethodologyStatus.APPROVED_FOR_PERSONAL_USE.value,
        MethodologyStatus.RETIRED.value,
    }
    if claimed_status not in allowed:
        return {
            "ok": False,
            "methodology_id": methodology_id,
            "reason": "invalid_status",
            "claimed_status": claimed_status,
        }
    # Prevent overstating beyond catalog without an approval record
    if claimed_status == MethodologyStatus.APPROVED_FOR_PERSONAL_USE.value:
        store = get_state_store()
        approvals = store.read_json(_NAMESPACE, "approvals", default={"keys": []}) or {}
        has_approval = any(
            str(k).startswith(f"{methodology_id}:") for k in list(approvals.get("keys") or [])
        )
        if not has_approval and current.get("status") != MethodologyStatus.APPROVED_FOR_PERSONAL_USE.value:
            return {
                "ok": False,
                "methodology_id": methodology_id,
                "reason": "approval_missing",
                "claimed_status": claimed_status,
                "catalog_status": current.get("status"),
            }
    return {
        "ok": True,
        "methodology_id": methodology_id,
        "catalog_status": current.get("status"),
        "claimed_status": claimed_status,
    }
