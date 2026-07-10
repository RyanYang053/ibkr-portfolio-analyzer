from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from app.db.legacy_bridge import read_json_with_legacy, write_json_state

_INVITATIONS: dict[str, dict[str, str]] = {}


def _hydrate() -> None:
    global _INVITATIONS
    if _INVITATIONS:
        return
    stored = read_json_with_legacy("users", "invitations", None, default={})
    if isinstance(stored, dict):
        _INVITATIONS.update(stored)


def create_invitation(
    email: str,
    role: str,
    invited_by: str,
    *,
    ttl_hours: int = 72,
) -> dict[str, str]:
    _hydrate()
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).isoformat()
    invitation = {
        "email": email.lower(),
        "role": role,
        "invited_by": invited_by,
        "expires_at": expires_at,
        "accepted_at": "",
    }
    _INVITATIONS[token] = invitation
    write_json_state("users", "invitations", _INVITATIONS)
    return {"token": token, **invitation}


def get_invitation(token: str) -> dict[str, str] | None:
    _hydrate()
    invitation = _INVITATIONS.get(token)
    if not invitation:
        return None
    expires_at = datetime.fromisoformat(invitation["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        return None
    if invitation.get("accepted_at"):
        return None
    return invitation


def accept_invitation(token: str) -> dict[str, str] | None:
    _hydrate()
    invitation = get_invitation(token)
    if not invitation:
        return None
    invitation["accepted_at"] = datetime.now(timezone.utc).isoformat()
    _INVITATIONS[token] = invitation
    write_json_state("users", "invitations", _INVITATIONS)
    return invitation


def list_invitations() -> list[dict[str, str]]:
    _hydrate()
    return [{"token": token, **payload} for token, payload in _INVITATIONS.items()]
