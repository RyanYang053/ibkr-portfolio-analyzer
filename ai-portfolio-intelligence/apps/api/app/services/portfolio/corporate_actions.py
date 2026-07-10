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
    description = (txn.description or "").strip()
    lowered = description.lower()

    if "split" in lowered or (txn.price == 0 and txn.quantity > 0 and not txn.amount):
        for pattern in SPLIT_PATTERNS:
            match = pattern.search(description)
            if match:
                numerator = float(match.group(1))
                denominator = float(match.group(2)) if match.lastindex and match.lastindex >= 2 else 1.0
                if denominator > 0:
                    return CorporateAction(action_type="split", ratio=numerator / denominator)
        if "reverse" in lowered:
            return CorporateAction(action_type="split", ratio=0.5)
        if txn.quantity > 0:
            # IBKR often records only the incremental shares from a 2-for-1 split.
            return CorporateAction(action_type="split_bonus", ratio=1.0)

    if "spinoff" in lowered or "spin-off" in lowered:
        child_symbol = None
        symbol_match = re.search(r"\b([A-Z]{1,5})\b", description.upper())
        if symbol_match:
            child_symbol = symbol_match.group(1)
        return CorporateAction(action_type="spinoff", ratio=1.0, child_symbol=child_symbol)

    if "merger" in lowered:
        return CorporateAction(action_type="merger", ratio=1.0)

    return None


def apply_corporate_action_to_lots(
    open_lots: Deque,
    action: CorporateAction,
    txn: Transaction,
) -> None:
    if action.action_type == "split":
        for lot in open_lots:
            lot.quantity *= action.ratio
            if action.ratio > 0:
                lot.cost_basis_per_share /= action.ratio
        return

    if action.action_type == "split_bonus":
        # Bonus shares from a split: increase quantity, keep total cost unchanged.
        for lot in open_lots:
            lot.quantity += lot.quantity
        return

    if action.action_type == "spinoff":
        # Spinoff shares are tracked separately; parent cost basis is unchanged here.
        return

    if action.action_type == "merger":
        for lot in open_lots:
            lot.quantity = 0.0
