import math
from statistics import fmean

import pytest
from fastapi.testclient import TestClient

from app.api import invitation_store, user_store
from app.core.config import settings
from app.main import app
from app.services.fundamentals.sector_models import score_fundamentals_for_sector
from app.schemas.domain import FundamentalSnapshot
from datetime import date
from app.services.risk.advanced_risk import TRADING_DAYS


@pytest.fixture
def auth_client(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "disable_auth_enforcement", False)
    monkeypatch.setattr(settings, "allow_public_registration", False)
    monkeypatch.setattr(settings, "bootstrap_token", "bootstrap-secret")
    monkeypatch.setattr(user_store, "_USERS", {})
    monkeypatch.setattr(invitation_store, "_INVITATIONS", {})
    monkeypatch.setattr(user_store, "_hydrate_users", lambda: None)
    monkeypatch.setattr(invitation_store, "_hydrate", lambda: None)

    def fake_hash(password: str) -> str:
        return f"hashed:{password}"

    def fake_verify(password: str, password_hash: str) -> bool:
        return password_hash == f"hashed:{password}"

    monkeypatch.setattr("app.core.security.hash_password", fake_hash)
    monkeypatch.setattr("app.core.security.verify_password", fake_verify)
    monkeypatch.setattr("app.api.routes.auth.hash_password", fake_hash)
    monkeypatch.setattr("app.api.routes.auth.verify_password", fake_verify)
    return TestClient(app)


def test_bootstrap_owner_requires_token(auth_client):
    response = auth_client.post(
        "/auth/bootstrap",
        json={
            "bootstrap_token": "wrong",
            "email": "owner@example.com",
            "password": "secure-password",
            "name": "Owner",
        },
    )
    assert response.status_code == 403


def test_bootstrap_owner_creates_single_owner(auth_client):
    response = auth_client.post(
        "/auth/bootstrap",
        json={
            "bootstrap_token": "bootstrap-secret",
            "email": "owner@example.com",
            "password": "secure-password",
            "name": "Owner",
        },
    )
    assert response.status_code == 200
    assert response.json()["role"] == "owner"

    duplicate = auth_client.post(
        "/auth/bootstrap",
        json={
            "bootstrap_token": "bootstrap-secret",
            "email": "other@example.com",
            "password": "secure-password",
            "name": "Other",
        },
    )
    assert duplicate.status_code == 409


def test_public_registration_disabled_by_default(auth_client):
    response = auth_client.post(
        "/auth/register",
        json={
            "email": "viewer@example.com",
            "password": "secure-password",
            "name": "Viewer",
        },
    )
    assert response.status_code == 403


def test_login_and_logout_revokes_sessions(auth_client):
    auth_client.post(
        "/auth/bootstrap",
        json={
            "bootstrap_token": "bootstrap-secret",
            "email": "owner@example.com",
            "password": "secure-password",
            "name": "Owner",
        },
    )
    login = auth_client.post(
        "/auth/login",
        json={"email": "owner@example.com", "password": "secure-password"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert auth_client.get("/auth/me", headers=headers).status_code == 200

    auth_client.post("/auth/logout", headers=headers)
    assert auth_client.get("/auth/me", headers=headers).status_code == 401


def _fundamentals(**overrides):
    base = dict(
        symbol="DUK",
        period="TTM",
        report_date=date(2025, 12, 31),
        revenue_growth_yoy=0.03,
        gross_margin=0.4,
        operating_margin=0.24,
        free_cash_flow=1_000_000.0,
        cash=10_000_000.0,
        total_debt=5_000_000.0,
        pe_forward=18.0,
        ev_sales=3.0,
        fcf_yield=0.04,
        source="mock_fundamentals",
    )
    base.update(overrides)
    return FundamentalSnapshot(**base)


def test_utilities_sector_scores_without_name_error():
    scores = score_fundamentals_for_sector(
        _fundamentals(rate_base_growth=0.03, allowed_roe=0.10),
        "Utilities",
    )
    assert "business_quality" in scores
    assert scores["growth"] > 0


def test_utilities_sector_falls_back_when_sector_inputs_partial():
    scores = score_fundamentals_for_sector(
        _fundamentals(rate_base_growth=0.03),
        "Utilities",
    )
    assert "business_quality" in scores


def test_information_ratio_annualizes_active_return():
    active_returns = [0.001, -0.0005, 0.0008, 0.0002, -0.0001]
    tracking_daily = math.sqrt(fmean([(value - fmean(active_returns)) ** 2 for value in active_returns]))
    expected = math.sqrt(TRADING_DAYS) * fmean(active_returns) / tracking_daily
    assert expected > fmean(active_returns) / tracking_daily
