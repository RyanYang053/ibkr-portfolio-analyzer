from fastapi.testclient import TestClient

from app.api.deps import get_broker_adapter
from app.main import app
from app.services.broker.mock_ibkr import MockIBKRAdapter


def test_chat_endpoint_fallback_without_gemini_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("app.services.ai.client.settings.gemini_api_key", None)
    monkeypatch.setattr("app.services.ai.client._runtime_api_key", None)
    
    app.dependency_overrides[get_broker_adapter] = lambda: MockIBKRAdapter()
    try:
        client = TestClient(app)

        payload = {
            "message": "Compare NVDA and AAPL margins and news.",
            "tagged_symbols": ["NVDA", "AAPL"],
            "history": [
                {"role": "user", "content": "Hello AI"},
                {"role": "model", "content": "Hello! How can I help you analyze your portfolio today?"}
            ]
        }

        response = client.post("/ai/chat", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert "response" in data
        response_text = data["response"]
        
        # Assert fallback details
        assert "Demo mode active" in response_text or "Gemini API connection error" in response_text
        assert "NVDA" in response_text
        assert "AAPL" in response_text
        assert "Current price" in response_text
        assert "Decision Support Suggestion" in response_text
        assert "does not execute trades" in response_text
    finally:
        app.dependency_overrides.clear()


def test_chat_endpoint_validation_errors():
    client = TestClient(app)
    
    # Message field missing
    payload = {
        "tagged_symbols": ["NVDA"],
        "history": []
    }
    response = client.post("/ai/chat", json=payload)
    assert response.status_code == 422
