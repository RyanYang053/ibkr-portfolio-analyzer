"""Personal product-scope claims and prohibited institutional wording."""

from __future__ import annotations

from enum import StrEnum


class ProductCapability(StrEnum):
    PERSONAL_ACCOUNTING = "personal_accounting"
    TAX_DECISION_SUPPORT = "tax_decision_support"
    PROXY_ATTRIBUTION = "proxy_attribution"
    PERSONAL_DECISION_SUPPORT = "personal_decision_support"
    BROKER_REPORTED_MARGIN = "broker_reported_margin"


PROHIBITED_CLAIMS: frozenset[str] = frozenset(
    {
        "institutional accounting",
        "official books and records",
        "filing-ready tax",
        "CRA certified",
        "registered investment advice",
        "official Brinson attribution",
        "broker-equivalent margin",
        "guaranteed recommendation",
    }
)

# Paths (relative to apps/api) where prohibited phrases may appear only to
# explain what the system does not provide.
CLAIM_SCAN_ALLOWLIST: frozenset[str] = frozenset(
    {
        "app/core/product_scope.py",
        "tests/test_product_claims.py",
        "../../docs/PRODUCT_SCOPE.md",
        "../../docs/compliance-boundaries.md",
        "../../docs/no-trading-policy.md",
        "../../web/components/Disclaimer.tsx",
        "../../web/components/attribution/MethodologyDisclosure.tsx",
        "../../web/components/risk/MarginCard.tsx",
    }
)

ACCOUNTING_DISCLAIMER = (
    "Portfolio accounting is reconciled against imported broker records. "
    "It is not an official broker statement or accounting book of record."
)

TAX_DISCLAIMER = (
    "This report is a tax reconciliation aid and not a filed tax return. "
    "Verify the results using CRA-certified tax software or a qualified "
    "tax professional before filing."
)

ATTRIBUTION_DISCLAIMER = (
    "Sector effects are estimated using sector proxies. This is not "
    "constituent-level attribution from the official benchmark provider."
)

DECISION_DISCLAIMER = (
    "These outputs are personalized analytical signals for the account "
    "owner. They are not instructions, orders, or a substitute for "
    "independent investment judgment."
)

MARGIN_DISCLAIMER = (
    "Current margin figures are broker-reported. Internal stress scenarios "
    "are estimates and may differ materially from IBKR liquidation or "
    "portfolio-margin calculations."
)

PRODUCT_SCOPE_SUMMARY = (
    "A secure, read-only, individually operated portfolio analytics and "
    "decision-support application using broker data, reconciliation controls, "
    "tax estimates, scenario analytics, and deterministic research lenses. "
    "Outputs are informational and require user review before action."
)
