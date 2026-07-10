from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Deque, Optional

from app.schemas.domain import Transaction

SPLIT_PATTERNS = (
    re.compile(r"(\d+(?:\.\d+)?)\s*(?:for|/)\s*(\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"split.*?(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"(\d+(?:\.\d+)?)\s*for\s*1", re.IGNORECASE),
)


@dataclass
class CorporateAction:
    action_type: str
    ratio: float
    child_symbol: Optional[str] = None


def parse_corporate_action(txn: Transaction) -> Optional[CorporateAction]:
    """Parse only explicit corporate-action descriptions. Never guess ratios."""
    description = (txn.description or "").strip()
    if not description:
        return None

    lowered = description.lower()
    if "split" not in lowered:
        return None

    for pattern in SPLIT_PATTERNS:
        match = pattern.search(description)
        if not match:
            continue
        numerator = float(match.group(1))
        denominator = float(match.group(2)) if match.lastindex and match.lastindex >= 2 else 1.0
        if denominator <= 0 or numerator <= 0:
            return None
        ratio = numerator / denominator
        if ratio <= 0:
            return None
        return CorporateAction(action_type="split", ratio=ratio)

    return None


def apply_corporate_action_to_lots(
    open_lots: Deque,
    action: CorporateAction,
    txn: Transaction,
) -> None:
    if action.action_type != "split":
        return
    for lot in open_lots:
        lot.quantity *= action.ratio
        if action.ratio > 0:
            lot.cost_basis_per_share /= action.ratio
