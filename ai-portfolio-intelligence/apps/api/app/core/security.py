from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from jose import jwt
from passlib.context import CryptContext

from app.api.user_store import get_user
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

OWNER_SCOPES = (
    "portfolio:read",
    "portfolio:write",
    "portfolio:sync",
    "configuration:write",
    "admin:audit",
)
VIEWER_SCOPES = ("portfolio:read",)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def scopes_for_role(role: str) -> tuple[str, ...]:
    return OWNER_SCOPES if role == "owner" else VIEWER_SCOPES


def create_access_token(subject: str, *, role: str | None = None) -> str:
    user = get_user(subject)
    resolved_role = role or (user.get("role", "viewer") if user else "viewer")
    token_version = int(user.get("token_version", "0")) if user else 0
    payload = {
        "sub": subject.lower(),
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.access_token_hours),
        "scope": " ".join(scopes_for_role(resolved_role)),
        "jti": uuid4().hex,
        "ver": token_version,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])


def token_is_revoked(payload: dict[str, Any]) -> bool:
    subject = str(payload.get("sub") or "").lower()
    if not subject:
        return True

    user = get_user(subject)
    if user is None:
        return True

    try:
        token_version = int(payload["ver"])
        current_version = int(user["token_version"])
    except (KeyError, TypeError, ValueError):
        return True

    return token_version != current_version
