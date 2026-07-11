from __future__ import annotations

from app.api import invitation_store
from app.core.security import token_is_revoked


def test_token_is_revoked_when_version_mismatch():
    payload = {"sub": "user@example.com", "ver": 0}

    def fake_get_user(email: str):
        return {"email": email, "token_version": "1"}

    import app.core.security as security

    original = security.get_user
    security.get_user = fake_get_user
    try:
        assert token_is_revoked(payload) is True
    finally:
        security.get_user = original


def test_token_is_revoked_when_user_missing():
    payload = {"sub": "missing@example.com", "ver": 0}

    import app.core.security as security

    original = security.get_user
    security.get_user = lambda _email: None
    try:
        assert token_is_revoked(payload) is True
    finally:
        security.get_user = original


def test_invitation_list_never_returns_token(monkeypatch):
    monkeypatch.setattr(
        invitation_store,
        "_INVITATIONS",
        {
            "secret-token": {
                "email": "new@example.com",
                "role": "viewer",
                "invited_by": "owner@example.com",
                "expires_at": "2099-01-01T00:00:00+00:00",
                "accepted_at": "",
            }
        },
    )
    monkeypatch.setattr(invitation_store, "_hydrate", lambda: None)

    rows = invitation_store.list_invitations()
    assert rows
    assert "token" not in rows[0]
    assert rows[0]["email"] == "new@example.com"
