from __future__ import annotations

from typing import Literal, Set

from fastapi import Depends, HTTPException
from pydantic import BaseModel

from app.core.config import is_desktop_local, settings
from app.core.request_context import bind_actor

OWNER_SCOPES: Set[str] = {
    "portfolio:read",
    "portfolio:write",
    "portfolio:sync",
    "configuration:write",
    "admin:audit",
}
VIEWER_SCOPES: Set[str] = {"portfolio:read"}


class Principal(BaseModel):
    user_id: str
    role: Literal["owner", "viewer"]
    scopes: Set[str]


def auth_enforcement_active() -> bool:
    # The product ships desktop-only with an invisible per-launch local session
    # token (LocalSessionMiddleware), not app login. There is no multi-user auth,
    # so there is nothing to enforce at the application layer.
    return False


def _desktop_local_principal() -> Principal:
    principal = Principal(
        user_id=settings.desktop_owner_id,
        role="owner",
        scopes=OWNER_SCOPES,
    )
    bind_actor(principal.user_id, tenant_id=principal.user_id)
    return principal


def get_current_principal() -> Principal:
    if is_desktop_local():
        return _desktop_local_principal()
    # Non-desktop (test/dev) runs as a single local owner; there is no login.
    principal = Principal(user_id="local-dev", role="owner", scopes=OWNER_SCOPES)
    bind_actor(principal.user_id, tenant_id=principal.user_id)
    return principal


def require_scope(scope: str):
    def dependency(principal: Principal = Depends(get_current_principal)) -> Principal:
        if scope not in principal.scopes:
            raise HTTPException(status_code=403, detail="Insufficient scope")
        return principal

    return dependency
