from __future__ import annotations

from fastapi import APIRouter, Depends

from ..security import require_admin

from ..services.firebase_service import FirebaseService


router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def list_audit_logs(admin: dict = Depends(require_admin)):
    logs = FirebaseService().list_collection("audit_logs", limit=200)
    return sorted(logs, key=lambda item: item.get("timestamp", ""), reverse=True)

