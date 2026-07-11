from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from app.api.account_access_store import grant_account_access, list_accessible_accounts, revoke_account_access
from app.api.auth_deps import Principal, get_current_principal, require_scope
from app.api.invitation_store import create_invitation, list_invitations
from app.api.user_store import list_users, update_user_role
from app.core.audit import get_audit_logs, log_audit_action

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(get_current_principal), Depends(require_scope("admin:audit"))],
)


class InvitationRequest(BaseModel):
    email: EmailStr
    role: str = Field(default="viewer", pattern="^(owner|viewer)$")


class AccountAccessRequest(BaseModel):
    email: EmailStr
    account_id: str


class RoleUpdateRequest(BaseModel):
    email: EmailStr
    role: str = Field(pattern="^(owner|viewer)$")


@router.get("/audit-logs")
def audit_logs():
    return get_audit_logs()


@router.get("/users")
def users():
    return list_users()


@router.post("/invitations")
def invite_user(payload: InvitationRequest, principal: Principal = Depends(get_current_principal)):
    invitation = create_invitation(str(payload.email), payload.role, principal.user_id)
    log_audit_action(
        action="user_invited",
        object_type="user",
        object_id=invitation["email"],
        actor_id=principal.user_id,
        metadata={"role": payload.role, "invited_by": principal.user_id},
        critical=True,
    )
    return invitation


@router.get("/invitations")
def invitations():
    return list_invitations()


@router.put("/users/role")
def set_user_role(payload: RoleUpdateRequest, principal: Principal = Depends(get_current_principal)):
    if payload.email.lower() == principal.user_id and payload.role != "owner":
        raise HTTPException(status_code=400, detail="Cannot demote the active owner session")
    updated = update_user_role(str(payload.email), payload.role)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    log_audit_action(
        action="user_role_updated",
        object_type="user",
        object_id=updated["email"],
        actor_id=principal.user_id,
        metadata={"role": payload.role},
        critical=True,
    )
    return updated


@router.get("/account-access/{email}")
def account_access(email: str):
    return {"email": email.lower(), "accounts": list_accessible_accounts(email)}


@router.post("/account-access")
def grant_access(payload: AccountAccessRequest, principal: Principal = Depends(get_current_principal)):
    grant_account_access(str(payload.email), payload.account_id)
    log_audit_action(
        action="account_access_granted",
        object_type="account",
        object_id=payload.account_id,
        actor_id=principal.user_id,
        metadata={"email": str(payload.email).lower(), "granted_by": principal.user_id},
        critical=True,
    )
    return {"email": str(payload.email).lower(), "accounts": list_accessible_accounts(str(payload.email))}


@router.delete("/account-access")
def revoke_access(payload: AccountAccessRequest, principal: Principal = Depends(get_current_principal)):
    revoke_account_access(str(payload.email), payload.account_id)
    log_audit_action(
        action="account_access_revoked",
        object_type="account",
        object_id=payload.account_id,
        actor_id=principal.user_id,
        metadata={"email": str(payload.email).lower(), "revoked_by": principal.user_id},
        critical=True,
    )
    return {"email": str(payload.email).lower(), "accounts": list_accessible_accounts(str(payload.email))}
