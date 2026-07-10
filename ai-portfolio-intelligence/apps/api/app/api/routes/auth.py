from pydantic import BaseModel, EmailStr, Field
from fastapi import APIRouter, Depends, HTTPException

from app.api.auth_deps import Principal, get_current_principal
from app.api.user_store import get_user, save_user
from app.core.security import create_access_token, hash_password, verify_password


router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10)
    name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/register")
def register(payload: RegisterRequest) -> dict[str, str]:
    if get_user(payload.email):
        raise HTTPException(status_code=409, detail="User already exists")
    save_user(
        payload.email,
        {
            "email": payload.email,
            "name": payload.name,
            "password_hash": hash_password(payload.password),
            "role": "owner",
        },
    )
    return {"email": payload.email, "name": payload.name, "role": "owner"}


@router.post("/login")
def login(payload: LoginRequest) -> dict[str, str]:
    user = get_user(payload.email)
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"access_token": create_access_token(payload.email), "token_type": "bearer"}


@router.post("/logout")
def logout() -> dict[str, str]:
    return {"status": "session_closed", "note": "JWT tokens are stateless; discard the client token."}


@router.get("/me")
def me(principal: Principal = Depends(get_current_principal)) -> dict[str, str]:
    user = get_user(principal.user_id)
    if user:
        return {"email": user["email"], "name": user["name"], "role": user["role"]}
    return {"email": principal.user_id, "name": principal.user_id, "role": principal.role}
