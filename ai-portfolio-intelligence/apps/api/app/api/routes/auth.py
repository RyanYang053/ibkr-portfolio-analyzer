from pydantic import BaseModel, EmailStr, Field
from fastapi import APIRouter, HTTPException

from app.core.security import create_access_token, hash_password, verify_password


router = APIRouter(prefix="/auth", tags=["auth"])
_USERS: dict[str, dict[str, str]] = {}


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10)
    name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/register")
def register(payload: RegisterRequest) -> dict[str, str]:
    if payload.email in _USERS:
        raise HTTPException(status_code=409, detail="User already exists")
    _USERS[payload.email] = {
        "email": payload.email,
        "name": payload.name,
        "password_hash": hash_password(payload.password),
        "role": "owner",
    }
    return {"email": payload.email, "name": payload.name, "role": "owner"}


@router.post("/login")
def login(payload: LoginRequest) -> dict[str, str]:
    user = _USERS.get(payload.email)
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"access_token": create_access_token(payload.email), "token_type": "bearer"}


@router.post("/logout")
def logout() -> dict[str, str]:
    return {"status": "session_closed"}


@router.get("/me")
def me() -> dict[str, str]:
    return {"email": "demo@example.com", "name": "Demo Owner", "role": "owner"}
