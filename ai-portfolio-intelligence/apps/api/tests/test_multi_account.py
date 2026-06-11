from fastapi.testclient import TestClient
from app.core.config import settings
from app.main import app

def test_multi_account_and_consolidation():
    # Force mock mode for test isolation
    orig_mode = settings.broker_mode
    settings.broker_mode = "mock_ibkr_readonly"
    try:
        client = TestClient(app)
        
        # 1. Test specific account query
        res = client.get("/portfolio/summary?account_id=MOCK-001")
        assert res.status_code == 200
        data = res.json()
        assert data["summary"]["account_id"] == "MOCK-001"
        assert len(data["positions"]) > 0
        
        # 2. Test consolidated account query
        res_all = client.get("/portfolio/summary?account_id=all")
        assert res_all.status_code == 200
        data_all = res_all.json()
        assert data_all["summary"]["account_id"] == "all"
        
        # 3. Test consolidated positions
        res_pos = client.get("/portfolio/positions?account_id=all")
        assert res_pos.status_code == 200
        positions = res_pos.json()
        assert len(positions) > 0
        assert all(p["account_id"] == "all" for p in positions)
        
        # 4. Test consolidated PnL history
        res_pnl = client.get("/portfolio/pnl-history?account_id=all")
        assert res_pnl.status_code == 200
        
        # 5. Record consolidated PnL snapshot
        res_record = client.post("/portfolio/pnl-history/record?account_id=all")
        assert res_record.status_code == 200
        assert res_record.json()["net_liquidation"] > 0
        
    finally:
        settings.broker_mode = orig_mode
