"""Release C1: Screener engine + /screeners API."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.schemas.screener import FilterOp, ScreenDefinition, ScreenFilter
from app.services.screening.engine import run_screen


def _defn(**kw) -> ScreenDefinition:
    base = dict(
        screen_id="scr_1",
        name="quality growth",
        filters=[
            ScreenFilter(field="revenue_growth_yoy", op=FilterOp.GTE, value=0.10),
            ScreenFilter(field="gross_margin", op=FilterOp.GTE, value=0.50),
        ],
    )
    base.update(kw)
    return ScreenDefinition(**base)


# ------------------------------------------------------------ engine


def test_engine_matches_and_ranks():
    metrics = {
        "AAA": {"revenue_growth_yoy": 0.20, "gross_margin": 0.60},
        "BBB": {"revenue_growth_yoy": 0.05, "gross_margin": 0.60},  # fails growth
        "CCC": {"revenue_growth_yoy": 0.30, "gross_margin": None},  # missing margin
    }
    run = run_screen(
        _defn(),
        account_id="A1",
        universe=[("AAA", "AAA:1"), ("BBB", "BBB:2"), ("CCC", "CCC:3")],
        metric_resolver=lambda s: metrics[s],
        owned_symbols={"AAA"},
    )
    by_symbol = {r.symbol: r for r in run.results}
    assert by_symbol["AAA"].research_ready is True
    assert by_symbol["AAA"].rank == 1  # most matched
    assert by_symbol["AAA"].portfolio_fit["already_owned"] is True
    assert "gross_margin gte 0.5" in by_symbol["BBB"].failed_criteria or any(
        "gross_margin" in c for c in by_symbol["BBB"].matched_criteria
    )
    assert "gross_margin" in by_symbol["CCC"].missing_data
    assert by_symbol["CCC"].research_ready is False


def test_missing_metric_is_never_a_silent_pass():
    run = run_screen(
        _defn(),
        account_id="A1",
        universe=[("ZZZ", "ZZZ:1")],
        metric_resolver=lambda s: {},  # no data at all
        owned_symbols=set(),
    )
    result = run.results[0]
    assert set(result.missing_data) == {"revenue_growth_yoy", "gross_margin"}
    assert result.research_ready is False
    assert result.is_buy_recommendation is False


# ------------------------------------------------------------ routes


def test_screener_route_lifecycle():
    orig = settings.broker_mode
    settings.broker_mode = "mock_ibkr_readonly"
    try:
        client = TestClient(app)
        created = client.post(
            "/screeners?account_id=MOCK-001",
            json={"name": "growth", "filters": [{"field": "revenue_growth_yoy", "op": "gte", "value": 0.0}]},
        )
        assert created.status_code == 200
        sid = created.json()["screen_id"]

        listed = client.get("/screeners?account_id=MOCK-001").json()
        assert listed["count"] >= 1

        run = client.post(f"/screeners/{sid}/run?account_id=MOCK-001")
        assert run.status_code == 200
        run_body = run.json()
        assert run_body["universe_size"] >= 0
        assert "not buy recommendations" in run_body["data_quality"]["note"]

        fetched = client.get(f"/screeners/runs/{run_body['run_id']}")
        assert fetched.status_code == 200

        # Promote a result (if any) to the research queue — never an order.
        if run_body["results"]:
            rid = run_body["results"][0]["result_id"]
            promoted = client.post(f"/screeners/results/{rid}/promote?account_id=MOCK-001")
            assert promoted.status_code == 200
            assert promoted.json()["order_generated"] is False
            assert promoted.json()["promoted_to"] == "research_queue"
    finally:
        settings.broker_mode = orig
