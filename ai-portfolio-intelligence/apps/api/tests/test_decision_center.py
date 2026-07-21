from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.services.decision_center.holding_context import build_holding_context
from app.services.decision_center.holding_decision import DECISION_ACTIONS, evaluate_holding_decision
from app.services.decision_center.thesis_service import put_thesis


def test_ordered_gates_data_insufficient_without_inputs():
    context = build_holding_context(
        account_id="A1",
        instrument_key="AAA:1",
        symbol="AAA",
    )
    decision = evaluate_holding_decision(context)
    assert decision["action"] == "Data insufficient"
    assert any(g["gate"] == "data_quality" for g in decision["gates"])
    assert decision["action"] in DECISION_ACTIONS
    assert decision["valuation_status"] == "withheld"


def test_review_thesis_when_data_present_but_thesis_missing():
    context = build_holding_context(
        account_id="A1",
        instrument_key="AAA:1",
        symbol="AAA",
        position={"portfolio_weight": 3.0},
        fundamentals={"return_on_equity": 0.2},
        risk_metrics={"max_drawdown_decimal": -0.10},
    )
    decision = evaluate_holding_decision(context)
    assert decision["action"] == "Review thesis"


def test_valuation_gate_blocks_add_without_approved_valuation():
    put_thesis("A1", "AAA:1", text="Long-term compounder with durable moat.")
    context = build_holding_context(
        account_id="A1",
        instrument_key="AAA:1",
        symbol="AAA",
        position={"portfolio_weight": 3.0},
        fundamentals={
            "return_on_equity": 0.25,
            "fcf_yield": 0.06,
            "operating_margin": 0.3,
            "total_debt": 5,
            "average_common_equity": 100,
        },
        risk_metrics={"volatility": 0.15, "max_drawdown_decimal": -0.10},
        thesis={"text": "Long-term compounder with durable moat."},
        valuation_status="withheld",
    )
    decision = evaluate_holding_decision(context)
    assert decision["action"] == "Review thesis"
    valuation_gate = next(g for g in decision["gates"] if g["gate"] in {"valuation", "valuation_status"})
    assert valuation_gate["passed"] is False


def test_no_action_when_gates_clear():
    put_thesis("A1", "AAA:1", text="Long-term compounder with durable moat.")
    context = build_holding_context(
        account_id="A1",
        instrument_key="AAA:1",
        symbol="AAA",
        position={"portfolio_weight": 3.0},
        fundamentals={
            "return_on_equity": 0.25,
            "fcf_yield": 0.06,
            "operating_margin": 0.3,
            "total_debt": 5,
            "average_common_equity": 100,
            "net_income_common": 40,
            "operating_cash_flow": 50,
            "cash": 30,
            "pe_forward": 15,
            "gross_margin": 0.5,
            "revenue_growth_yoy": 0.1,
        },
        risk_metrics={"volatility": 0.15, "max_drawdown_decimal": -0.10, "conditional_var_95": 0.05},
        factor_exposures={"quality": 0.4, "market": 0.05, "value": 0.1, "momentum": 0.0},
        liquidity={"participation_rate": 0.04},
        thesis={"text": "Long-term compounder with durable moat."},
        tax_flags={"methodology_status": "available"},
        valuation_status="approved",
    )
    decision = evaluate_holding_decision(context)
    assert decision["action"] in DECISION_ACTIONS
    assert decision["action"] != "Data insufficient"
    assert any(g["gate"] in {"methodology", "implementation", "lens_synthesis", "valuation"} for g in decision["gates"])
    assert decision["order_generated"] is False
    assert any(s.get("scenario_type") == "no_trade" for s in (decision.get("scenarios") or []))

def test_load_holding_market_inputs_uses_real_providers(monkeypatch):
    from app.services.decision_center import market_inputs

    monkeypatch.setattr(
        market_inputs,
        "load_fundamentals_for_symbol",
        lambda symbol, **_: {"return_on_equity": 0.2, "symbol": symbol},
    )
    monkeypatch.setattr(
        market_inputs,
        "load_account_risk_bundle",
        lambda **_: (
            {"volatility": 12.0, "max_drawdown": 8.0, "conditional_var_95": 4.0},
            {"Market": 0.1, "Value": 0.2, "Momentum": -0.05, "Quality": 0.3},
        ),
    )
    summary = SimpleNamespace(account_id="A1", net_liquidation=100000.0, base_currency="USD")
    payload = market_inputs.load_holding_market_inputs(
        symbol="AAA",
        account_id="A1",
        positions=[],
        summary=summary,
    )
    assert payload["fundamentals"]["return_on_equity"] == 0.2
    assert payload["risk_metrics"]["volatility"] == 12.0
    assert payload["factor_exposures"]["market"] == 0.1
    assert payload["factor_exposures"]["value"] == 0.2
    assert payload["factor_exposures"]["quality"] == 0.3


def test_load_holding_market_inputs_fails_closed_when_unavailable(monkeypatch):
    from app.services.decision_center import market_inputs

    monkeypatch.setattr(market_inputs, "load_fundamentals_for_symbol", lambda symbol, **_: None)
    monkeypatch.setattr(market_inputs, "load_account_risk_bundle", lambda **_: ({}, {}))
    summary = SimpleNamespace(account_id="A1", net_liquidation=100000.0, base_currency="USD")
    payload = market_inputs.load_holding_market_inputs(
        symbol="ZZZ",
        account_id="A1",
        positions=[],
        summary=summary,
    )
    assert payload["fundamentals"] == {}
    assert payload["risk_metrics"] == {}
    assert payload["factor_exposures"] == {}


def test_thesis_persists_via_json_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.persistence_backend", "json")
    monkeypatch.setattr("app.db.state_store._data_dir", lambda: str(tmp_path))
    from app.db import holding_thesis_repo
    from app.services.decision_center import thesis_service

    # Clear any process-local residue and force repo-backed path.
    if hasattr(thesis_service, "_THESIS_STORE"):
        thesis_service._THESIS_STORE.clear()

    saved = thesis_service.put_thesis("ACC-1", "AAA:9", text="Durable franchise.", author="tester")
    assert saved["version"] == 1
    assert saved["text"] == "Durable franchise."

    # Simulate process restart: clear in-memory if still present, reload from store.
    if hasattr(thesis_service, "_THESIS_STORE"):
        thesis_service._THESIS_STORE.clear()
    loaded = thesis_service.get_thesis("ACC-1", "AAA:9")
    assert loaded is not None
    assert loaded["text"] == "Durable franchise."
    assert loaded["version"] == 1

    versions = holding_thesis_repo.list_thesis_versions("ACC-1", "AAA:9")
    assert len(versions) == 1
    assert versions[0]["thesis_text"] == "Durable franchise."

    again = thesis_service.put_thesis("ACC-1", "AAA:9", text="Updated thesis.", author="tester")
    assert again["version"] == 2
    versions = holding_thesis_repo.list_thesis_versions("ACC-1", "AAA:9")
    assert len(versions) == 2


def test_monitoring_rules_persist_via_json_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.persistence_backend", "json")
    monkeypatch.setattr("app.db.state_store._data_dir", lambda: str(tmp_path))
    from app.services.decision_center import monitoring_rules

    if hasattr(monitoring_rules, "_RULES"):
        monitoring_rules._RULES.clear()

    rule = monitoring_rules.create_monitoring_rule(
        "ACC-2",
        instrument_key="BBB:1",
        rule_type="drawdown",
        threshold=15.0,
        note="alert",
    )
    assert rule["active"] is True
    if hasattr(monitoring_rules, "_RULES"):
        monitoring_rules._RULES.clear()
    listed = monitoring_rules.list_monitoring_rules("ACC-2")
    assert len(listed) == 1
    assert listed[0]["rule_id"] == rule["rule_id"]
    assert listed[0]["threshold"] == 15.0


def test_monitoring_rule_evaluation_triggers_concentration(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.persistence_backend", "json")
    monkeypatch.setattr("app.db.state_store._data_dir", lambda: str(tmp_path))
    from app.services.decision_center import monitoring_rules

    rule = monitoring_rules.create_monitoring_rule(
        "ACC-MON",
        instrument_key="AAA:1",
        rule_type="concentration",
        threshold=8.0,
        note="size",
    )
    assert rule["instrument_key"] == "AAA:1"
    listed = monitoring_rules.list_monitoring_rules("ACC-MON")
    assert listed
    result = monitoring_rules.evaluate_monitoring_rules(
        "ACC-MON",
        holdings=[{"instrument_key": "AAA:1", "portfolio_weight": 12.0}],
        risk_metrics={"max_drawdown_decimal": -0.1},
        theses={},
    )
    assert result["rules_evaluated"] >= 1
    assert result["evaluations"]
    assert any(item.get("triggered") for item in result["evaluations"])
    assert any(alert.get("triggered") for alert in result["alerts"])
    assert result["alert_delivery"] == "desktop_inbox"


def test_action_simulator_uses_tax_and_risk_blocks():
    from app.services.decision_center.action_simulator import simulate_holding_action

    sim = simulate_holding_action(
        action="Review trim",
        current_weight=10.0,
        proposed_weight=5.0,
        summary=SimpleNamespace(net_liquidation=100000.0, base_currency="USD"),
        risk_metrics={"max_drawdown_decimal": -0.12},
        account_type="IRA",
        symbol="AAA",
        account_id="A1",
    )
    assert sim["direction"] == "reduce"
    assert sim["implementation_ready"] is False
    assert sim["tax"]["estimated_tax"] == 0.0
    assert sim["risk"]["over_concentrated_after"] is False


def test_tax_transition_inputs_and_lot_snapshots_json_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.persistence_backend", "json")
    monkeypatch.setattr("app.db.state_store._data_dir", lambda: str(tmp_path))
    from app.db import tax_lot_snapshot_repo, tax_transition_inputs_repo

    saved = tax_transition_inputs_repo.upsert_tax_transition_inputs(
        account_id="TAX-1",
        jurisdiction="US",
        account_type="Taxable",
        tax_budget=5000.0,
        available_loss_offsets=1000.0,
        wash_sale_window_days=30,
        superficial_loss_window_days=30,
        effective_date=date(2026, 7, 15),
        source="optimizer",
        constraints={"note": "test"},
    )
    latest = tax_transition_inputs_repo.get_latest_tax_transition_inputs("TAX-1")
    assert latest is not None
    assert latest["tax_budget"] == 5000.0
    assert latest["account_id"] == saved["account_id"]

    lots = tax_lot_snapshot_repo.replace_tax_lot_snapshots(
        account_id="TAX-1",
        as_of_date=date(2026, 7, 15),
        lots=[
            {
                "symbol": "AAPL",
                "con_id": 265598,
                "quantity": 10,
                "cost_basis_per_share": 150.0,
                "acquired_date": date(2025, 1, 2),
                "currency": "USD",
                "jurisdiction": "US",
                "lot_method": "FIFO",
                "source": "optimizer",
                "payload": {"lot_id": "lot-1"},
            }
        ],
    )
    assert len(lots) == 1
    listed = tax_lot_snapshot_repo.list_tax_lot_snapshots("TAX-1", as_of_date=date(2026, 7, 15))
    assert len(listed) == 1
    assert listed[0]["symbol"] == "AAPL"
    assert listed[0]["quantity"] == 10
