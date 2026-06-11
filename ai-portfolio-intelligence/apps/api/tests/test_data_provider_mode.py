from fastapi.testclient import TestClient

from app.main import app


def test_stock_data_provider_endpoints_do_not_return_mock_data_by_default():
    client = TestClient(app)

    for path in [
        "/stocks/MSFT/fundamentals",
        "/stocks/MSFT/technicals",
        "/stocks/MSFT/valuation",
        "/stocks/MSFT/news",
    ]:
        response = client.get(path)
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "DATA_PROVIDER_NOT_CONFIGURED"
