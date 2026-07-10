from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from app.core.config import settings
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
    if settings.persistence_backend == "postgres":
        from app.db.invitation_repo import create_invitation as create_pg

        plaintext, metadata = create_pg(email, role, invited_by, ttl_hours=ttl_hours)
        return {"token": plaintext, **metadata}

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
    if settings.persistence_backend == "postgres":
        from app.db.invitation_repo import get_invitation_by_token

        invitation = get_invitation_by_token(token)
        if invitation is None:
            return None
        return {
            "email": invitation["email"],
            "role": invitation["role"],
            "invited_by": invitation["invited_by"],
            "expires_at": invitation["expires_at"] or "",
            "accepted_at": invitation.get("accepted_at") or "",
        }

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
    if settings.persistence_backend == "postgres":
        return get_invitation(token)

    _hydrate()
    invitation = get_invitation(token)
    if not invitation:
        return None
    invitation["accepted_at"] = datetime.now(timezone.utc).isoformat()
    _INVITATIONS[token] = invitation
    write_json_state("users", "invitations", _INVITATIONS)
    return invitation


def list_invitations() -> list[dict[str, str]]:
    if settings.persistence_backend == "postgres":
        from app.db.invitation_repo import list_invitations as list_pg

        return list_pg()

    _hydrate()
    return [
        {
            "email": payload["email"],
            "role": payload["role"],
            "invited_by": payload["invited_by"],
            "expires_at": payload["expires_at"],
            "accepted_at": payload.get("accepted_at") or "",
        }
        for payload in _INVITATIONS.values()
    ]
