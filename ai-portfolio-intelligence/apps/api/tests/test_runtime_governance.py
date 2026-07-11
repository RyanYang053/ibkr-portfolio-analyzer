from __future__ import annotations

import pytest

from app.services.governance.runtime_gate import enforce_or_mark_experimental, gate_production_output
from app.services.methodology_registry import DEFAULT_METHODOLOGIES
from app.services.model_governance import MethodologyNotApproved, require_methodology_status


def test_pnl_reconciliation_is_experimental():
    record = next(item for item in DEFAULT_METHODOLOGIES if item.methodology_id == "portfolio_pnl_reconciliation")
    assert record.approval_status == "experimental"


def test_require_methodology_status_blocks_unapproved():
    with pytest.raises(MethodologyNotApproved):
        require_methodology_status("portfolio_pnl_reconciliation")


def test_runtime_gate_marks_experimental_output():
    gate = gate_production_output("portfolio_optimizer")
    assert gate["allowed"] is False
    payload = enforce_or_mark_experimental("portfolio_optimizer", {"result": "ok"}, production=True)
    assert payload["status"] == "withheld_unapproved_methodology"
    assert payload["professional_language_allowed"] is False
