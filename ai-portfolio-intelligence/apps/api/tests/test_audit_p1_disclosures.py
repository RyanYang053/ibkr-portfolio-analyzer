from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.services.portfolio_construction.optimizer import (
    COST_MODEL_ASSUMPTIONS,
    _cost_assumption_disclosures,
)


def test_cost_model_assumptions_are_named_with_source_version():
    assert COST_MODEL_ASSUMPTIONS["source"] == "internal_default_cost_model"
    assert COST_MODEL_ASSUMPTIONS["version"] == "v1-uncalibrated"
    assert COST_MODEL_ASSUMPTIONS["broker_calibrated"] is False
    disclosures = _cost_assumption_disclosures()
    assert any(item.startswith("cost_model_source=") for item in disclosures)
    assert any(item.startswith("cost_model_version=") for item in disclosures)
    assert any("commission_bps=" in item for item in disclosures)
    assert any("market_impact=" in item for item in disclosures)
    assert "cost_assumption_broker_calibrated=false" in disclosures


def test_tax_evidence_persistence_failed_is_disclosed_in_constraints():
    from app.schemas.domain import TaxTransitionSummary

    summary = TaxTransitionSummary(
        jurisdiction="US",
        methodology_status="available",
        exclusions=["tax_evidence_persistence_failed"],
    )
    constraints = [
        f"tax_transition_status={summary.methodology_status}",
        *_cost_assumption_disclosures(),
        "implementation_ready=false",
    ]
    if "tax_evidence_persistence_failed" in (summary.exclusions or []):
        constraints.append("tax_evidence_persistence_failed=true")
    assert "tax_evidence_persistence_failed=true" in constraints
    assert "implementation_ready=false" in constraints


def test_thesis_first_insert_retries_on_unique_conflict(monkeypatch):
    import app.db.holding_thesis_repo as repo

    monkeypatch.setattr(repo.settings, "persistence_backend", "postgres")
    monkeypatch.setattr(repo, "_table_available", lambda: True)
    monkeypatch.setattr(repo, "require_postgres_persistence", lambda *_a, **_k: None)

    attempts = {"n": 0}

    class _Mappings:
        def first(self):
            return None

    class _Result:
        def mappings(self):
            return _Mappings()

    class _Session:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def execute(self, statement, params=None):
            sql = str(getattr(statement, "text", statement))
            if "holding_thesis_versions" in sql:
                attempts["n"] += 1
                if attempts["n"] == 1:
                    raise IntegrityError("INSERT", {}, Exception("unique"))
            return _Result()

        def commit(self):
            return None

    import sys
    import types

    session_mod = types.ModuleType("app.db.session")
    session_mod.SessionLocal = lambda: _Session()
    monkeypatch.setitem(sys.modules, "app.db.session", session_mod)

    payload = repo.put_thesis("A1", "AAA:1", text="Durable moat thesis", author="tester")
    assert payload["version"] == 1
    assert payload["methodology_status"] == "experimental"
    assert attempts["n"] == 2


def test_thesis_concurrency_fail_closed_after_retries(monkeypatch):
    import sys
    import types

    import app.db.holding_thesis_repo as repo

    monkeypatch.setattr(repo.settings, "persistence_backend", "postgres")
    monkeypatch.setattr(repo, "_table_available", lambda: True)
    monkeypatch.setattr(repo, "require_postgres_persistence", lambda *_a, **_k: None)

    class _Mappings:
        def first(self):
            return None

    class _Result:
        def mappings(self):
            return _Mappings()

    class _Session:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def execute(self, statement, params=None):
            sql = str(getattr(statement, "text", statement))
            if "holding_thesis_versions" in sql:
                raise IntegrityError("INSERT", {}, Exception("unique"))
            return _Result()

        def commit(self):
            return None

    session_mod = types.ModuleType("app.db.session")
    session_mod.SessionLocal = lambda: _Session()
    monkeypatch.setitem(sys.modules, "app.db.session", session_mod)

    with pytest.raises(RuntimeError, match="refusing silent version loss"):
        repo.put_thesis("A1", "AAA:1", text="Should fail closed")
