from __future__ import annotations

from typing import Literal, Set

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from app.api.user_store import get_user
from app.core.config import settings
from app.core.request_context import bind_actor
from app.core.security import decode_access_token, token_is_revoked

bearer_scheme = HTTPBearer(auto_error=False)

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


def _principal_for_email(email: str) -> Principal:
    user = get_user(email)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    role = user.get("role", "viewer")
    scopes = OWNER_SCOPES if role == "owner" else VIEWER_SCOPES
    principal = Principal(user_id=email, role=role, scopes=scopes)
    bind_actor(principal.user_id, tenant_id=principal.user_id)
    return principal


def auth_enforcement_active() -> bool:
    if settings.disable_auth_enforcement:
        return False
    return True


def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Principal:
    if not auth_enforcement_active():
        bootstrap = settings.bootstrap_owner_email
        if bootstrap and get_user(bootstrap):
            return _principal_for_email(bootstrap)
        principal = Principal(user_id="local-dev", role="owner", scopes=OWNER_SCOPES)
        bind_actor(principal.user_id, tenant_id=principal.user_id)
        return principal

    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        payload = decode_access_token(credentials.credentials)
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid access token") from exc

    if token_is_revoked(payload):
        raise HTTPException(status_code=401, detail="Session has been revoked")

    subject = payload.get("sub")
    if not subject:
        raise HTTPException(status_code=401, detail="Token subject is missing")
    return _principal_for_email(str(subject))


def require_scope(scope: str):
    def dependency(principal: Principal = Depends(get_current_principal)) -> Principal:
        if scope not in principal.scopes:
            raise HTTPException(status_code=403, detail="Insufficient scope")
        return principal

    return dependency
