"""Account role assignment helpers."""

from __future__ import annotations

from app.schemas.financial_plan import AccountRole

DEFAULT_ROLE_BY_HINT: dict[str, str] = {
    "ira": "tax_advantaged",
    "roth": "tax_advantaged",
    "401k": "tax_advantaged",
    "hsa": "tax_advantaged",
    "margin": "taxable",
    "joint": "taxable",
    "individual": "taxable",
}


def suggest_account_role(account_id: str, *, account_label: str | None = None) -> AccountRole:
    label = (account_label or account_id or "").lower()
    role = "growth"
    tax_wrapper = "other"
    for hint, mapped in DEFAULT_ROLE_BY_HINT.items():
        if hint in label:
            role = mapped
            tax_wrapper = hint if hint in {"ira", "401k", "hsa"} else "taxable"
            break
    return AccountRole(
        account_id=account_id,
        role=role,
        tax_wrapper=tax_wrapper,
        contribution_priority=1,
        notes="Suggested role — confirm in plan builder",
    )


def merge_account_roles(
    existing: list[AccountRole],
    account_ids: list[str],
) -> list[AccountRole]:
    by_id = {r.account_id: r for r in existing}
    for account_id in account_ids:
        if account_id not in by_id:
            by_id[account_id] = suggest_account_role(account_id)
    return list(by_id.values())
