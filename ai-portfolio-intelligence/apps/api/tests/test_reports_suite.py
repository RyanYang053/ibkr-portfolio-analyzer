"""Release F1: monthly review + trade-plan report (§22)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.schemas.trade_plan import TradeDirection, TradePlan
from app.services.reports.builders import build_trade_plan_report, render_report_html


def test_trade_plan_report_builder_and_html():
    plan = TradePlan(
        trade_plan_id="tp_r", account_id="A1", instrument_id="MSFT:1", symbol="MSFT",
        direction=TradeDirection.BUY, proposed_quantity=100.0, invalidation_price=380.0, target_high=500.0,
    )
    report = build_trade_plan_report(plan)
    assert report["report_type"] == "trade_plan_report"
    assert report["order_generated"] is False
    assert report["sizing"]["proposed_quantity"] == 100.0
    html_out = render_report_html(report)
    assert "<title>" in html_out and "MSFT" in html_out


def test_monthly_and_trade_plan_report_endpoints():
    orig = settings.broker_mode
    settings.broker_mode = "mock_ibkr_readonly"
    try:
        client = TestClient(app)
        monthly = client.post("/reports/monthly?account_id=MOCK-001")
        assert monthly.status_code == 200
        body = monthly.json()
        assert body["report_type"] == "monthly_investment_review"
        assert "performance" in body and "risk" in body and "trade_process_analytics" in body
        # Unavailable sections are withheld honestly, not fabricated.
        assert body["tax_activity"]["status"] == "unavailable"

        html_resp = client.post("/reports/monthly?account_id=MOCK-001&format=html")
        assert html_resp.status_code == 200
        assert "text/html" in html_resp.headers["content-type"]

        pid = client.post(
            "/trade-plans", json={"account_id": "MOCK-001", "instrument_id": "MSFT:1", "direction": "buy"}
        ).json()["trade_plan_id"]
        tp_report = client.post(f"/reports/trade-plan/{pid}")
        assert tp_report.status_code == 200
        assert tp_report.json()["report_type"] == "trade_plan_report"
        assert client.post("/reports/trade-plan/nope").status_code == 404
    finally:
        settings.broker_mode = orig
