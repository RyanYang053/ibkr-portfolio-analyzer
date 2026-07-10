from pydantic import BaseModel, EmailStr, Field
from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.auth_deps import Principal, get_current_principal
from app.api.invitation_store import accept_invitation, get_invitation
from app.api.account_access_store import grant_account_access
from app.api.account_deps import WILDCARD_ACCOUNT
from app.api.user_store import bump_token_version, get_user, owner_exists, save_user
from app.core.config import settings
from app.core.rate_limit import check_login_allowed, clear_login_failures, record_login_failure
from app.core.security import create_access_token, hash_password, verify_password


router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10)
    name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class BootstrapRequest(BaseModel):
    bootstrap_token: str
    email: EmailStr
    password: str = Field(min_length=10)
    name: str


class AcceptInviteRequest(BaseModel):
    token: str
    password: str = Field(min_length=10)
    name: str


@router.post("/bootstrap")
def bootstrap_owner(payload: BootstrapRequest) -> dict[str, str]:
    if not settings.bootstrap_token:
        raise HTTPException(status_code=503, detail="Bootstrap token is not configured")
    if payload.bootstrap_token != settings.bootstrap_token:
        raise HTTPException(status_code=403, detail="Invalid bootstrap token")

    email = str(payload.email).lower()
    password_hash = hash_password(payload.password)

    if settings.persistence_backend == "postgres":
        from app.api.user_store import _hydrate_users
        from app.db.user_repo import bootstrap_owner_transactionally

        user = bootstrap_owner_transactionally(email, password_hash, payload.name)
        _hydrate_users()
        from app.api import user_store

        user_store._USERS[email] = user
    else:
        if owner_exists():
            raise HTTPException(status_code=409, detail="An owner account already exists")
        if get_user(email):
            raise HTTPException(status_code=409, detail="User already exists")
        save_user(
            email,
            {
                "email": email,
                "name": payload.name,
                "password_hash": password_hash,
                "role": "owner",
                "token_version": "0",
            },
        )
        grant_account_access(email, WILDCARD_ACCOUNT)

    return {
        "email": email,
        "name": payload.name,
        "role": "owner",
        "access_token": create_access_token(email, role="owner"),
        "token_type": "bearer",
    }


@router.post("/register")
def register(payload: RegisterRequest) -> dict[str, str]:
    if not settings.allow_public_registration:
        raise HTTPException(status_code=403, detail="Public registration is disabled")
    email = str(payload.email).lower()
    if get_user(email):
        raise HTTPException(status_code=409, detail="User already exists")
    save_user(
        email,
        {
            "email": email,
            "name": payload.name,
            "password_hash": hash_password(payload.password),
            "role": "viewer",
            "token_version": "0",
        },
    )
    return {"email": email, "name": payload.name, "role": "viewer"}


@router.post("/accept-invite")
def accept_invite(payload: AcceptInviteRequest) -> dict[str, str]:
    invitation = get_invitation(payload.token)
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation is invalid or expired")
    email = invitation["email"]
    if get_user(email):
        raise HTTPException(status_code=409, detail="User already exists")
    accepted = accept_invitation(payload.token)
    if not accepted:
        raise HTTPException(status_code=404, detail="Invitation is invalid or expired")
    save_user(
        email,
        {
            "email": email,
            "name": payload.name,
            "password_hash": hash_password(payload.password),
            "role": invitation["role"],
            "token_version": "0",
        },
    )
    return {
        "email": email,
        "name": payload.name,
        "role": invitation["role"],
        "access_token": create_access_token(email, role=invitation["role"]),
        "token_type": "bearer",
    }


@router.post("/login")
def login(payload: LoginRequest, request: Request) -> dict[str, str]:
    email = str(payload.email).lower()
    check_login_allowed(request, email)
    user = get_user(email)
    if not user or not verify_password(payload.password, user["password_hash"]):
        record_login_failure(request, email)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    clear_login_failures(request, email)
    role = user.get("role", "viewer")
    return {
        "access_token": create_access_token(email, role=role),
        "token_type": "bearer",
        "email": email,
        "name": user.get("name", email),
        "role": role,
    }


@router.post("/logout")
def logout(principal: Principal = Depends(get_current_principal)) -> dict[str, str]:
    bump_token_version(principal.user_id)
    return {"status": "session_closed", "note": "All active sessions for this user have been revoked."}


@router.get("/me")
def me(principal: Principal = Depends(get_current_principal)) -> dict[str, str]:
    user = get_user(principal.user_id)
    if user:
        return {"email": user["email"], "name": user["name"], "role": user["role"]}
    return {"email": principal.user_id, "name": principal.user_id, "role": principal.role}
