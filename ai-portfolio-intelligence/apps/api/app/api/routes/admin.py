from fastapi import APIRouter, Depends

from app.api.auth_deps import get_current_principal, require_scope
from app.core.audit import get_audit_logs


router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(get_current_principal), Depends(require_scope("admin:audit"))],
)


@router.get("/audit-logs")
def audit_logs():
    return get_audit_logs()
