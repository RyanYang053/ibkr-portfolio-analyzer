"""Personal product-scope claims and prohibited institutional wording."""

from __future__ import annotations

from enum import StrEnum


class ProductCapability(StrEnum):
    PERSONAL_ACCOUNTING = "personal_accounting"
    TAX_DECISION_SUPPORT = "tax_decision_support"
    TAX_FILING_WORKSHEET = "tax_filing_worksheet"
    PROXY_ATTRIBUTION = "proxy_attribution"
    PERSONAL_DECISION_SUPPORT = "personal_decision_support"
    BROKER_REPORTED_MARGIN = "broker_reported_margin"
    OPTIONS_REGT_MARGIN = "options_regt_margin"


PROHIBITED_CLAIMS: frozenset[str] = frozenset(
    {
        "institutional accounting",
        "official books and records",
        "CRA certified",
        "registered investment advice",
        "official Brinson attribution",
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
    "Filing worksheets are available when tax_lot_methodology is approved_for_personal_use "
    "and lots are reconciled. This is not a filed tax return — have a qualified tax "
    "professional review before filing."
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
    "Reg T style margin worksheets are available when options_margin_regt is "
    "approved_for_personal_use. Broker-reported figures and IBKR Portfolio Margin "
    "(TIMS) may differ; confirm requirements with your broker before liquidation decisions."
)

PRODUCT_SCOPE_SUMMARY = (
    "A secure, read-only, individually operated portfolio analytics and "
    "decision-support application using broker data, reconciliation controls, "
    "tax estimates, scenario analytics, and deterministic research lenses. "
    "Outputs are informational and require user review before action."
)
