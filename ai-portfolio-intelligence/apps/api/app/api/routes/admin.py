from fastapi import APIRouter
from app.core.audit import get_audit_logs


router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/audit-logs")
def audit_logs():
    return get_audit_logs()
